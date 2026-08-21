import asyncio
import contextlib
from typing import Any

from moonlighter.application.answers.option_matcher import match_option_locally
from moonlighter.application.appliers.base import BaseApplier, classify_submit_outcome, is_skip
from moonlighter.core.log import get_logger

logger = get_logger(__name__)

# SmartRecruiters' own web-components library: every real form control carries its
# label as a plain HTML attribute (confirmed live, 2026-07-22) -- no proximity
# heuristic needed, unlike the other three appliers.
_FIELD_TAGS = (
    "spl-input",
    "spl-select",
    "spl-dropdown",
    "spl-textarea",
    "spl-autocomplete",
    "spl-phone-field",
)
_FIELD_SELECTOR = ", ".join(f"{tag}[label]" for tag in _FIELD_TAGS)
_CLOSED_SET_TAGS = {"spl-select", "spl-dropdown"}
# Generous cap for any real wizard; guards against an infinite Next-click loop if a
# step's DOM shape confuses _is_final_step.
_MAX_WIZARD_STEPS = 6
# SmartRecruiters has no <form>/input[type=submit] -- classify_submit_outcome's
# default form_visible_js looks for those and would never fire "still visible" here.
_SR_FORM_VISIBLE_JS = "() => !!document.querySelector('spl-form-field')"


def _log_fill_stats(status: dict[str, str]) -> None:
    filled = sum(1 for s in status.values() if s == "filled")
    failed = [label for label, s in status.items() if s.startswith("failed")]
    skipped = sum(1 for s in status.values() if s == "skipped")
    logger.info("fill_form: %d filled, %d failed, %d skipped", filled, len(failed), skipped)
    if failed:
        logger.warning("fill_form: fields with failures: %s", failed)


class SmartRecruitersApplier(BaseApplier):
    """Bespoke applier for SmartRecruiters' Angular Web-Components apply flow
    ("oneclick-ui").

    Unlike Greenhouse/Recruitee/Workable, this does NOT reuse CustomDropdownFiller
    -- SmartRecruiters' spl-* custom-element library is architecturally different
    from the react-select pattern that class was built for. Closed-set fields
    (spl-select/spl-dropdown) use the ATS-agnostic match_option_locally helper
    directly instead. The apply flow is a multi-step wizard (a "Next" spl-button
    between steps): fill_form() walks every step but stops before the final action
    button -- submit() remains the separate, explicit last step.

    LIVE-VERIFY GATE: live-confirmed only the first wizard step (Personal
    information + Experience + Education) on 2 real postings (Western Digital,
    ServiceNow, 2026-07-22). The content of subsequent step(s) (likely
    screening/EEO questions), the spl-dropzone upload widget, and the
    spl-autocomplete "City" field were NOT exercised in a real fill -- their
    handlers are written from static DOM inspection, not a live fill_application
    run. Do not treat this class as "done" until fill_application has been run
    end-to-end against a real open SmartRecruiters job and the final screenshot
    reviewed.
    """

    async def detect(self) -> bool:
        match = "jobs.smartrecruiters.com" in self.page.url and "oneclick-ui" in self.page.url
        if match:
            logger.debug("detect: smartrecruiters ✓ (%s)", self.page.url)
        return match

    async def extract_fields(self) -> tuple[list[str], frozenset[str]]:
        els = await self.page.query_selector_all(_FIELD_SELECTOR)
        labels: list[str] = []
        closed_set: set[str] = set()
        for el in els:
            label = await el.get_attribute("label")
            if not label:
                continue
            labels.append(label)
            tag = await el.evaluate("el => el.tagName.toLowerCase()")
            if tag in _CLOSED_SET_TAGS:
                closed_set.add(label)
        logger.debug("extract_fields: %d fields", len(labels))
        return labels, frozenset(closed_set)

    async def fill_form(self, answers: dict[str, str], cv_path: str) -> dict[str, str]:
        """Fills the form across every wizard step. Returns
        {label: "filled"|"skipped"|"failed:<reason>"} accumulated over all steps,
        plus "__cv__" (and "__wizard__" if navigation itself failed). Never
        raises. Stops before the final submit action -- submit() is a separate,
        explicit step."""
        logger.info("fill_form: start (%d answers)", len(answers))
        status: dict[str, str] = {}
        remaining = dict(answers)
        cv_done = not cv_path
        for step in range(1, _MAX_WIZARD_STEPS + 1):
            step_labels, _ = await self.extract_fields()
            for label in step_labels:
                if label in remaining:
                    status[label] = await self._fill_one(label, remaining.pop(label))
            if not cv_done and await self.page.query_selector("spl-dropzone"):
                status["__cv__"] = await self._upload_cv(cv_path)
                cv_done = True
            if await self._is_final_step():
                break
            if not await self._click_next():
                status["__wizard__"] = f"failed:navigation_at_step_{step}"
                break
        else:
            status["__wizard__"] = "failed:wizard_too_long"
        if "__cv__" not in status:
            status["__cv__"] = "skipped"
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
            tag = await field.evaluate("el => el.tagName.toLowerCase()")
            if tag in _CLOSED_SET_TAGS:
                return await self._fill_closed_set(field, label_text, answer)
            if tag == "spl-autocomplete":
                return await self._fill_autocomplete(field, label_text, answer)
            native = await field.query_selector("input, textarea")
            if native is None:
                return "failed:no_native_control"
            await native.fill(answer)
            await asyncio.sleep(0.2)
            return "filled"
        except Exception as e:
            logger.debug("fill_form: exception in '%s': %s", label_text, e)
            return f"failed:{type(e).__name__}"

    async def _find_field(self, label_text: str) -> Any:
        escaped = label_text.replace('"', '\\"')
        selector = ", ".join(f'{tag}[label="{escaped}"]' for tag in _FIELD_TAGS)
        return await self.page.query_selector(selector)

    async def _fill_closed_set(self, field: Any, label_text: str, answer: str) -> str:
        """spl-select/spl-dropdown: open, match the answer against the visible
        option texts locally (no LLM fallback in this version), click the exact
        match. No confirmed match -> "failed:custom_dropdown", never a guess."""
        try:
            await field.click()
            await asyncio.sleep(0.4)
            option_els = await self.page.query_selector_all("spl-select-option, spl-dropdown-item")
            pairs = []
            for el in option_els:
                text = (await el.inner_text()).strip()
                if text:
                    pairs.append((text, el))
            options = [text for text, _ in pairs]
            choice = match_option_locally(answer, options)
            if choice is None:
                logger.warning(
                    "_fill_closed_set: '%s' no match for '%s'. Options: %s",
                    label_text,
                    answer,
                    options,
                )
                with contextlib.suppress(Exception):
                    await self.page.keyboard.press("Escape")
                return "failed:custom_dropdown"
            for text, el in pairs:
                if text == choice:
                    await el.click()
                    await asyncio.sleep(0.2)
                    return "filled"
            return "failed:custom_dropdown"  # pragma: no cover - choice is always one of `pairs`
        except Exception as e:
            logger.warning("_fill_closed_set: '%s' exception — %s", label_text, e)
            return f"failed:{type(e).__name__}"

    async def _fill_autocomplete(self, field: Any, label_text: str, answer: str) -> str:
        """spl-autocomplete (e.g. "City"): types the answer and clicks the first
        suggestion if one appears; if no suggestion list renders, the typed text
        stays in the field as a plain value (some autocompletes accept free text)."""
        try:
            native = await field.query_selector("input")
            if native is None:
                return "failed:no_native_control"
            await native.click()
            await native.type(answer, delay=30)
            await asyncio.sleep(0.6)
            suggestion = await self.page.query_selector("spl-dropdown-item, [role='option'], li")
            if suggestion:
                await suggestion.click()
                await asyncio.sleep(0.2)
            return "filled"
        except Exception as e:
            logger.debug("_fill_autocomplete: '%s' exception — %s", label_text, e)
            return f"failed:{type(e).__name__}"

    async def _upload_cv(self, cv_path: str) -> str:
        if not cv_path:
            return "skipped"
        try:
            dropzone = await self.page.query_selector("spl-dropzone")
            file_input = None
            if dropzone:
                file_input = await dropzone.query_selector("input[type='file']")
            if file_input is None:
                file_input = await self.page.query_selector("input[type='file']")
            if file_input is None:
                logger.warning("_upload_cv: no input[type='file'] found")
                return "failed:no_file_input"
            await file_input.set_input_files(cv_path)
            await asyncio.sleep(1)
            logger.info("_upload_cv: CV attached")
            return "filled"
        except Exception as e:
            logger.warning("_upload_cv: exception — %s", e)
            return f"failed:{type(e).__name__}"

    async def _is_final_step(self) -> bool:
        """True when the current step's primary button is the final action
        (anything other than "Next"/"Continue"), or when there's no primary
        button at all (nothing left this applier can click)."""
        btn = await self.page.query_selector("spl-button[type='primary']")
        if not btn:
            return True
        text = (await btn.inner_text()).strip().lower()
        return text not in ("next", "continue")

    async def _click_next(self) -> bool:
        try:
            btn = await self.page.query_selector("spl-button[type='primary']")
            if not btn:
                return False
            await btn.click()
            await self.page.wait_for_load_state("networkidle", timeout=10000)
            return True
        except Exception as e:
            logger.warning("_click_next: failed — %s", e)
            return False

    async def submit(self) -> str:
        logger.info("submit: click")
        try:
            btn = await self.page.query_selector("spl-button[type='primary']")
            if not btn:
                logger.warning("submit: button not found")
                return "failed"
            await btn.click()
            await self.page.wait_for_load_state("networkidle", timeout=15000)
            outcome = await classify_submit_outcome(self.page, form_visible_js=_SR_FORM_VISIBLE_JS)
            if outcome.startswith("failed:validation_errors"):
                logger.warning("submit: form still visible after submit — %s", outcome)
            else:
                logger.info("submit: outcome=%s", outcome)
            return outcome
        except Exception as e:
            logger.warning("submit: exception — %s", e)
            return "failed"
