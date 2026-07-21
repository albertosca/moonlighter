import asyncio
from typing import Any, ClassVar

from moonlighter.application.appliers.base import (
    BaseApplier,
    _detect_closed_set,
    classify_submit_outcome,
    fill_field,
    is_skip,
    query_labels_with_fallback,
)
from moonlighter.application.appliers.custom_dropdown import CustomDropdownFiller
from moonlighter.core.log import get_logger
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

logger = get_logger(__name__)

# Labels of the CV/resume upload area — the attachment is handled by _upload_cv, so
# these must not go to the LLM as text fields (or they'd get a garbage answer).
# Mirrors greenhouse.py's _UPLOAD_LABELS; Recruitee's dropzone widget is commonly
# labeled "Resume/CV" or "Upload your resume/CV".
_UPLOAD_LABELS = {
    "resume/cv",
    "resume / cv",
    "upload your resume/cv",
    "cover letter",
    "attach",
    "anexar",
}


def _log_fill_stats(status: dict[str, str]) -> None:
    filled = sum(1 for s in status.values() if s == "filled")
    failed = [label for label, s in status.items() if s.startswith("failed")]
    skipped = sum(1 for s in status.values() if s == "skipped")
    logger.info("fill_form: %d filled, %d failed, %d skipped", filled, len(failed), skipped)
    if failed:
        logger.warning("fill_form: fields with failures: %s", failed)


class RecruiteeApplier(BaseApplier):
    """Bespoke applier for Recruitee's client-rendered (React SPA) apply form.

    Mirrors GreenhouseApplier's shape (fill_form/_fill_one/_find_field/_upload_cv,
    CustomDropdownFiller reuse, uniform S-12 status dict) — Recruitee, like
    Greenhouse, mixes native inputs with custom combobox widgets for
    single/multi-select questions.

    LIVE-VALIDATION GATE: every selector below was chosen from static research of
    Recruitee's public apply pages, not a live browser session. Each assumption
    that needs confirmation on a real job is flagged inline with
    `# LIVE-VERIFY:`. Do not treat this class as "done" until `fill_application`
    has been run against a real open Recruitee job and the `03-filled` screenshot
    reviewed.
    """

    SOURCE: ClassVar[str] = "recruitee"

    def __init__(self, page: Page, config: dict[str, Any], profile: dict[str, Any]):
        super().__init__(page, config, profile)
        self._dropdown = CustomDropdownFiller(page, config, profile)

    async def detect(self) -> bool:
        # LIVE-VERIFY: recruitee.com only matches the default *.recruitee.com career
        # site. Most real Recruitee companies use fully custom career-page domains
        # (the employer's own domain, proxied to Recruitee's backend) that this host
        # check cannot see — those are now routed by `service.detect_applier`'s
        # source-first pass (scanner-tagged `source="recruitee"`), which returns this
        # applier without calling detect() at all. This URL check remains only as the
        # fallback for the rare case where `source` isn't available.
        match = "recruitee.com" in self.page.url
        if match:
            logger.debug("detect: recruitee ✓ (%s)", self.page.url)
        return match

    async def extract_fields(self) -> tuple[list[str], frozenset[str]]:
        await self._open_application()
        # LIVE-VERIFY: Recruitee renders questions inside a form built from React
        # components; the exact wrapper class (kaleidoscope design-system classes
        # change across versions) is unconfirmed. `label` covers the semantic case
        # (label[for]/wraps-input); the other two selectors are best-guess
        # fallbacks pending a live DOM inspection.
        label_els = await query_labels_with_fallback(
            self.page,
            ["label", "[data-testid*='question'] label", "[class*='question'] label"],
        )
        labels = []
        closed_set: set[str] = set()
        for el in label_els:
            text = (await el.inner_text()).strip()
            if text and text.lower() not in _UPLOAD_LABELS:
                labels.append(text)
                if await _detect_closed_set(el):
                    closed_set.add(text)
        logger.debug("extract_fields: %d fields", len(labels))
        return labels, frozenset(closed_set)

    async def _open_application(self) -> None:
        """Clicks the 'Apply' button when the form is not yet open.

        LIVE-VERIFIED (Ziflow, a real *.recruitee.com posting, 2026-07-20): the
        real CTA carries data-cy='apply-button' and switches a tab panel to
        reveal the form (labels exist in the DOM but are not visible/fillable
        until clicked). The other selectors are kept as fallbacks for Recruitee
        instances that render differently.
        """
        try:
            apply_btn = await self.page.query_selector(
                "[data-cy='apply-button'], a#apply-button, button#apply-button, "
                "a[href='#apply'], button[data-testid='apply-button']"
            )
            if apply_btn:
                await apply_btn.click()
                await self.page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            pass

    async def fill_form(self, answers: dict[str, str], cv_path: str) -> dict[str, str]:
        """Fills the form. Returns {label: "filled"|"skipped"|"failed:<reason>"}.
        Never raises — failures go into the return value and the log. Stops
        before submit (submit() is a separate, explicit step)."""
        logger.info("fill_form: start (%d answers)", len(answers))
        status = {label: await self._fill_one(label, answer) for label, answer in answers.items()}
        if cv_path:
            status["__cv__"] = await self._upload_cv(cv_path)
        _log_fill_stats(status)
        return status

    async def _fill_one(self, label_text: str, answer: str) -> str:
        if is_skip(answer):
            return "skipped"
        try:
            field = await self._find_field(label_text)
            if field is None:
                logger.debug("fill_form: field not found — '%s'", label_text)
                return "failed:not_found"

            # LIVE-VERIFY: is_custom_combobox's heuristic (role=combobox /
            # aria-haspopup / classname containing "select__input") was validated
            # against Greenhouse's react-select markup. Recruitee's own combobox
            # widget (single/multi-select questions, e.g. "How did you hear about
            # us?") may use different roles/classnames — confirm live whether this
            # detects it, or whether Recruitee needs its own heuristic.
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
        ElementHandle or None. Same cascade as GreenhouseApplier — kept
        byte-similar since neither ATS's exact DOM has been confirmed live yet.

        LIVE-VERIFY: strategy #1 (get_by_label) assumes Recruitee associates
        `label[for]`/`aria-labelledby` correctly with its inputs, including for
        the custom combobox widgets. If Recruitee wraps the input inside the
        label without a `for` attribute, this cascade still works via
        get_by_label's implicit-association handling in Playwright — but that is
        unconfirmed without a live page.
        """
        for exact in (True, False):
            locator = self.page.get_by_label(label_text, exact=exact)
            if await locator.count() > 0:
                return await locator.first.element_handle()

        # LIVE-VERIFY: JS fallback assumes plain <label for="..."> markup, same as
        # Greenhouse. Confirm against a real Recruitee question block.
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

        # 3) direct aria-label
        escaped = label_text.replace("'", "\\'")
        return await self.page.query_selector(f"[aria-label='{escaped}']")

    async def _upload_cv(self, cv_path: str) -> str:
        """Attaches the CV. Returns "filled", "skipped" or "failed:<reason>".

        LIVE-VERIFY: Recruitee's resume upload is a drag-and-drop "dropzone"
        widget; the actual file input is expected to be a hidden
        `input[type='file']` inside it (same pattern as Greenhouse), but the
        wrapping markup (react-dropzone classnames, whether the input is
        rendered lazily only after a click on the dropzone) is unconfirmed.
        """
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
        """Labels with '*' whose input/select is visibly empty before submit.
        Mirrors GreenhouseApplier's check — advisory only, never blocks submit."""
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
        # LIVE-VERIFY: assumes a single-step form with one submit button
        # (button[type='submit']). If Recruitee's flow is multi-step (a "Next"
        # button per section before a final submit), this will click the wrong
        # button or fail to find one — confirm against a real job.
        logger.info("submit: click")
        try:
            submit_btn = await self.page.query_selector(
                "button[type='submit'], input[type='submit']"
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
