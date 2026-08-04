import asyncio
from typing import Any

from moonlighter.application.answers.option_matcher import match_option_locally
from moonlighter.application.appliers.base import (
    BaseApplier,
    _detect_closed_set,
    classify_submit_outcome,
    discover_radio_groups,
    fill_field,
    is_skip,
    query_by_aria_label,
    query_labels_with_fallback,
    select_radio_option,
)
from moonlighter.application.appliers.custom_dropdown import CustomDropdownFiller
from moonlighter.core.log import get_logger
from playwright.async_api import Page

logger = get_logger(__name__)

# Labels of the CV/resume upload area -- the attachment is handled by _upload_cv, so
# these must not go to the LLM as text fields. Mirrors greenhouse.py's _UPLOAD_LABELS.
_UPLOAD_LABELS = {
    "resume",
    "resume/cv",
    "cv",
    "cover letter",
}


def _log_fill_stats(status: dict[str, str]) -> None:
    filled = sum(1 for s in status.values() if s == "filled")
    failed = [label for label, s in status.items() if s.startswith("failed")]
    skipped = sum(1 for s in status.values() if s == "skipped")
    logger.info("fill_form: %d filled, %d failed, %d skipped", filled, len(failed), skipped)
    if failed:
        logger.warning("fill_form: fields with failures: %s", failed)


class WorkableApplier(BaseApplier):
    """Bespoke applier for Workable's apply form.

    Mirrors GreenhouseApplier's shape (fill_form/_fill_one/_find_field/_upload_cv,
    CustomDropdownFiller reuse, uniform S-12 status dict) -- live-verified
    (2026-07-21) to be structurally close to Greenhouse: standard Personal
    information section (First/Last name, Email, Phone, Address), Profile
    section (Resume upload, optional Cover letter), Submit application button
    with type="submit" (same generic selector as Greenhouse works unchanged).

    Unlike Greenhouse, there's no "click Apply first" gate: discovery's
    application_url already points directly at the apply form
    (https://apply.workable.com/j/{id}/apply), confirmed live -- so this
    applier has no _open_application() step.

    LIVE-VERIFY GATE (see design spec): neither posting checked during design
    had a custom screening question (dropdown/radio) -- the CustomDropdownFiller
    path below is written by analogy with Greenhouse/Recruitee, not yet
    confirmed against a real Workable posting that has one.
    """

    def __init__(self, page: Page, config: dict[str, Any], profile: dict[str, Any]):
        super().__init__(page, config, profile)
        self._dropdown = CustomDropdownFiller(page, config, profile)

    async def detect(self) -> bool:
        match = "apply.workable.com" in self.page.url
        if match:
            logger.debug("detect: workable ✓ (%s)", self.page.url)
        return match

    async def extract_fields(self) -> tuple[list[str], frozenset[str]]:
        label_els = await query_labels_with_fallback(
            self.page,
            ["label", "[data-ui='field'] label", "[class*='field'] label"],
        )
        radio_groups = await self._radio_groups()
        option_texts = {o.lower() for g in radio_groups.values() for o in g["options"]}

        labels = []
        closed_set: set[str] = set()
        for el in label_els:
            text = (await el.inner_text()).strip()
            if not text or text.lower() in _UPLOAD_LABELS:
                continue
            # Every screening question here is labelled YES/NO. Left in, four
            # distinct required questions collapse into two dict keys and the
            # questions themselves are lost.
            if text.lower() in option_texts:
                continue
            labels.append(text)
            if await _detect_closed_set(el):
                closed_set.add(text)

        for question in radio_groups:
            labels.append(question)
            closed_set.add(question)

        logger.debug("extract_fields: %d fields", len(labels))
        return labels, frozenset(closed_set)

    async def _radio_groups(self) -> dict[str, dict[str, Any]]:
        """{question: {options, name}} for every radio group on the page."""
        return {g["question"]: g for g in await discover_radio_groups(self.page)}

    async def fill_form(self, answers: dict[str, str], cv_path: str) -> dict[str, str]:
        """Fills the form. Returns {label: "filled"|"skipped"|"failed:<reason>"}.
        Never raises -- failures go into the return value and the log."""
        logger.info("fill_form: start (%d answers)", len(answers))
        status = {label: await self._fill_one(label, answer) for label, answer in answers.items()}
        status["__cv__"] = await self._upload_cv(cv_path)
        _log_fill_stats(status)
        return status

    async def _fill_one(self, label_text: str, answer: str) -> str:
        if is_skip(answer):
            return "skipped"
        group = (await self._radio_groups()).get(label_text)
        if group is not None:
            chosen = match_option_locally(answer, group["options"])
            if chosen is None:
                logger.warning(
                    "fill_form: no option of %s matches %r — '%s'",
                    group["options"],
                    answer[:60],
                    label_text,
                )
                return "failed:no_matching_option"
            if not await select_radio_option(self.page, group["name"], chosen):
                return "failed:radio_option_not_clickable"
            logger.debug("fill_form: radio '%s' → %r", label_text, chosen)
            return "filled"
        try:
            field = await self._find_field(label_text)
            if field is None:
                logger.debug("fill_form: field not found — '%s'", label_text)
                return "failed:not_found"

            if await self._dropdown.is_custom_combobox(field):
                ok = await self._dropdown.select_custom_option(field, label_text, answer)
                return "filled" if ok else "failed:custom_dropdown"

            tag = await field.evaluate("el => el.tagName.toLowerCase()")
            if tag in ("input", "textarea", "select"):
                await fill_field(field, answer)
                await asyncio.sleep(0.2)
                return "filled"

            ok = await self._dropdown.fill_custom_element(field, label_text, answer)
            return "filled" if ok else "failed:custom_element_unsupported"
        except Exception as e:
            logger.debug("fill_form: exception in '%s': %s", label_text, e)
            return f"failed:{type(e).__name__}"

    async def _find_field(self, label_text: str) -> Any:
        """Locates the input associated with a label, in cascade. Returns the
        ElementHandle or None."""
        for exact in (True, False):
            locator = self.page.get_by_label(label_text, exact=exact)
            if await locator.count() > 0:
                return await locator.first.element_handle()

        for_id = await self.page.evaluate(
            """(text) => {
                const target = text.replace(/[*\\u00a0]+/g, ' ').replace(/\\s+/g, ' ').trim().toLowerCase();
                for (const l of document.querySelectorAll('label')) {
                    const clean = l.innerText.replace(/[*\\u00a0]+/g, ' ').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (clean === target || clean.startsWith(target)) return l.getAttribute('for');
                }
                return null;
            }""",
            label_text,
        )
        if for_id:
            el = await self.page.query_selector(f"#{for_id}")
            if el:
                return el

        # The label goes as an argument, never spliced into a selector: a label
        # carrying a newline made query_selector raise BADSTRING, which surfaced
        # as failed:Error on fields that were perfectly fine.
        return await query_by_aria_label(self.page, label_text)

    async def _upload_cv(self, cv_path: str) -> str:
        """Attaches the CV. Returns "filled", "skipped" or "failed:<reason>"."""
        if not cv_path:
            return "skipped"
        try:
            file_locator = self.page.locator("input[type='file']").first
            if await file_locator.count() > 0:
                await file_locator.set_input_files(cv_path)
                await asyncio.sleep(1)
                logger.info("_upload_cv: CV attached via locator")
                return "filled"

            file_input = await self.page.query_selector("input[type='file']")
            if file_input:
                await file_input.set_input_files(cv_path)
                await asyncio.sleep(1)
                logger.info("_upload_cv: CV attached via query_selector")
                return "filled"

            logger.warning("_upload_cv: no input[type='file'] found")
            return "failed:no_file_input"
        except Exception as e:
            logger.warning("_upload_cv: exception — %s", e)
            return f"failed:{type(e).__name__}"

    async def submit(self) -> str:
        empty = await self._empty_required_fields()
        if empty:
            logger.warning("submit: %d required field(s) empty: %s", len(empty), empty)
        return await self._click_submit_and_classify()

    async def _empty_required_fields(self) -> list[str]:
        """Labels with '*' whose input/select is visibly empty before submit."""
        logger.info("submit: checking required fields")
        empty: list[str] = await self.page.evaluate("""() => {
            const empty = [];
            for (const label of document.querySelectorAll('label')) {
                if (!label.textContent.includes('*')) continue;
                const forId = label.getAttribute('for');
                if (!forId) continue;
                const el = document.getElementById(forId);
                if (!el) continue;
                const tag = el.tagName.toLowerCase();
                if ((tag === 'input' || tag === 'textarea') && !el.value.trim()) {
                    empty.push(label.innerText.trim());
                } else if (tag === 'select' && !el.value) {
                    empty.push(label.innerText.trim());
                }
            }
            return empty;
        }""")
        return empty

    async def _click_submit_and_classify(self) -> str:
        logger.info("submit: click")
        try:
            submit_btn = await self.page.query_selector(
                "input[type='submit'], button[type='submit']"
            )
            if not submit_btn:
                logger.warning("submit: button not found")
                return "failed"
            await submit_btn.click()
            await self.page.wait_for_load_state("networkidle", timeout=15000)

            outcome = await classify_submit_outcome(self.page)
            if outcome.startswith("failed:validation_errors"):
                logger.warning("submit: form still visible after submit — %s", outcome)
            else:
                logger.info("submit: outcome=%s", outcome)
            return outcome
        except Exception as e:
            logger.warning("submit: exception — %s", e)
            return "failed"
