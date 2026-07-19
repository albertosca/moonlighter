import asyncio
from typing import Any

from moonlighter.application.appliers.base import (
    BaseApplier,
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
_UPLOAD_LABELS = {
    "resume/cv",
    "cover letter",
    "attach",
    "anexar",
    "enter manually",
    "informe manualmente",
}


def _log_fill_stats(status: dict[str, str]) -> None:
    filled = sum(1 for s in status.values() if s == "filled")
    failed = [label for label, s in status.items() if s.startswith("failed")]
    skipped = sum(1 for s in status.values() if s == "skipped")
    logger.info("fill_form: %d filled, %d failed, %d skipped", filled, len(failed), skipped)
    if failed:
        logger.warning("fill_form: fields with failures: %s", failed)


class GreenhouseApplier(BaseApplier):
    def __init__(self, page: Page, config: dict[str, Any], profile: dict[str, Any]):
        super().__init__(page, config, profile)
        self._dropdown = CustomDropdownFiller(page, config, profile)

    async def detect(self) -> bool:
        match = "greenhouse.io" in self.page.url or "boards.greenhouse.io" in self.page.url
        if match:
            logger.debug("detect: greenhouse ✓ (%s)", self.page.url)
        return match

    async def extract_fields(self) -> list[str]:
        await self._open_application()
        label_els = await query_labels_with_fallback(
            self.page,
            ["label, .field-label", ".application-question label", "[data-field-label]"],
        )
        labels = []
        for el in label_els:
            text = (await el.inner_text()).strip()
            if text and text.lower() not in _UPLOAD_LABELS:
                labels.append(text)
        logger.debug("extract_fields: %d fields", len(labels))
        return labels

    async def _open_application(self) -> None:
        """Clicks the 'Apply' button when the form is not yet open."""
        try:
            apply_btn = await self.page.query_selector(
                "a#apply, button#apply, a[data-greenhouse-job-board-apply]"
            )
            if apply_btn:
                await apply_btn.click()
                await self.page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            pass

    async def fill_form(self, answers: dict[str, str], cv_path: str) -> dict[str, str]:
        """Fills the form. Returns {label: "filled"|"skipped"|"failed:<reason>"}.
        Never raises — failures go into the return value and the log."""
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
        # 1) get_by_label (resolves for/aria-label/labelledby + normalizes text)
        for exact in (True, False):
            locator = self.page.get_by_label(label_text, exact=exact)
            if await locator.count() > 0:
                return await locator.first.element_handle()

        # 2) JS: normalizes the label (strip *, &nbsp;, spaces) and grabs the `for` attribute
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
        """Attaches the CV. Returns "filled", "skipped" or "failed:<reason>". Tries
        locator (resilient to hidden inputs) and then query_selector."""
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
