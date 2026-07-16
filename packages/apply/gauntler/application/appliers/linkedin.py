import asyncio

from gauntler.application.appliers.base import BaseApplier, _is_skip
from gauntler.core.log import get_logger
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
            from gauntler.application.appliers.base import _query_labels_with_fallback

            label_els = await _query_labels_with_fallback(
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

    async def fill_form(self, answers: dict[str, str], cv_path: str) -> None:
        for label_text, answer in answers.items():
            if _is_skip(answer):
                logger.debug("skipping sentinel answer for %r", label_text)
                continue
            try:
                label = await self.page.query_selector(
                    f".jobs-easy-apply-modal label:text-is('{label_text}')"
                )
                if not label:
                    continue
                for_id = await label.get_attribute("for")
                if for_id:
                    field = await self.page.query_selector(f"#{for_id}")
                    if field:
                        from gauntler.application.appliers.base import _fill_field

                        await _fill_field(field, answer)
                        await asyncio.sleep(0.4)
            except Exception as e:
                logger.debug("skipping field %r: %s", label_text, e)
                continue
        # Upload CV if file input exists in the modal
        try:
            file_input = await self.page.query_selector(".jobs-easy-apply-modal input[type='file']")
            if file_input and cv_path:
                await file_input.set_input_files(cv_path)
                await asyncio.sleep(1)
        except Exception as e:
            logger.debug("CV upload failed: %s", e)

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
                    from gauntler.application.appliers.base import classify_submit_outcome

                    # Para o LinkedIn, "form ainda visível" = modal Easy Apply aberto.
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
