import asyncio

from moonlighter.application.appliers.base import (
    BaseApplier,
    classify_submit_outcome,
    fill_field,
    is_skip,
    query_labels_with_fallback,
)
from moonlighter.core.log import get_logger
from playwright.async_api import TimeoutError as PlaywrightTimeout

logger = get_logger(__name__)


class LinkedInApplier(BaseApplier):
    async def detect(self) -> bool:
        return "linkedin.com/jobs" in self.page.url

    async def is_easy_apply(self) -> bool:
        btn = await self.page.query_selector(".jobs-apply-button--top-card .artdeco-button")
        if not btn:
            return False
        text = (await btn.inner_text()).strip().lower()
        return "easy apply" in text

    async def extract_fields(self) -> list[str]:
        # Click Easy Apply button to open the modal
        try:
            btn = await self.page.query_selector(".jobs-apply-button--top-card .artdeco-button")
            if btn:
                await btn.click()
                await asyncio.sleep(2)
        except Exception:
            return []

        fields = []
        try:
            await self.page.wait_for_selector(".jobs-easy-apply-modal", timeout=10000)
            label_els = await query_labels_with_fallback(
                self.page,
                [
                    ".jobs-easy-apply-modal label, .jobs-easy-apply-modal .fb-dash-form-element__label",
                    ".jobs-easy-apply-content label",
                    "[data-easy-apply-form] label",
                ],
            )
            for el in label_els:
                text = (await el.inner_text()).strip()
                if text:
                    fields.append(text)
        except PlaywrightTimeout:
            pass
        return fields

    async def fill_form(self, answers: dict[str, str], cv_path: str) -> dict[str, str]:
        """Fill the Easy Apply modal fields and, if given, upload the CV.

        Returns a per-field status dict (label -> "filled"|"skipped"|"failed:<reason>",
        plus "__cv__") so partial fill failures surface instead of silently reaching
        submit (S-12)."""
        status = {label: await self._fill_one(label, answer) for label, answer in answers.items()}
        if cv_path:
            status["__cv__"] = await self._upload_cv(cv_path)
        return status

    async def _fill_one(self, label_text: str, answer: str) -> str:
        if is_skip(answer):
            return "skipped"
        try:
            label = await self.page.query_selector(
                f".jobs-easy-apply-modal label:text-is('{label_text}')"
            )
            if not label:
                return "failed:not_found"
            for_id = await label.get_attribute("for")
            if not for_id:
                return "failed:not_found"
            field = await self.page.query_selector(f"#{for_id}")
            if not field:
                return "failed:not_found"
            await fill_field(field, answer)
            await asyncio.sleep(0.4)
            return "filled"
        except Exception as e:
            logger.debug("fill failed for %r: %s", label_text, e)
            return f"failed:{type(e).__name__}"

    async def _upload_cv(self, cv_path: str) -> str:
        try:
            file_input = await self.page.query_selector(".jobs-easy-apply-modal input[type='file']")
            if file_input:
                await file_input.set_input_files(cv_path)
                await asyncio.sleep(1)
                return "filled"
            return "failed:not_found"
        except Exception as e:
            logger.debug("CV upload failed: %s", e)
            return f"failed:{type(e).__name__}"

    async def submit(self) -> str:
        """Click through multi-step Easy Apply and submit."""
        for _ in range(10):  # max 10 steps
            try:
                submit_btn = await self.page.query_selector(
                    "button[aria-label='Submit application'], button:text('Submit application')"
                )
                if submit_btn:
                    await submit_btn.click()
                    await asyncio.sleep(2)
                    # For LinkedIn, "form still visible" = the Easy Apply modal is open.
                    return await classify_submit_outcome(
                        self.page,
                        form_visible_js="() => !!document.querySelector('.jobs-easy-apply-modal')",
                        extra_text_markers=("application sent", "your application was sent"),
                    )
                next_btn = await self.page.query_selector(
                    "button[aria-label='Continue to next step'], button:text('Next'), button:text('Review')"
                )
                if next_btn:
                    await next_btn.click()
                    await asyncio.sleep(1.5)
                else:
                    break
            except Exception:
                break
        return "failed"
