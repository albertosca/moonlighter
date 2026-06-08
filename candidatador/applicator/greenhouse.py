import asyncio
from playwright.async_api import TimeoutError as PlaywrightTimeout
from candidatador.applicator.base import BaseApplier

class GreenhouseApplier(BaseApplier):
    async def detect(self) -> bool:
        return "greenhouse.io" in self.page.url or "boards.greenhouse.io" in self.page.url

    async def extract_fields(self) -> list[str]:
        """Navigate to the application form and extract all field labels."""
        try:
            apply_btn = await self.page.query_selector("a#apply, button#apply, a[data-greenhouse-job-board-apply]")
            if apply_btn:
                await apply_btn.click()
                await self.page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            pass

        labels = []
        from candidatador.applicator.base import _query_labels_with_fallback
        label_els = await _query_labels_with_fallback(self.page, [
            "label, .field-label",
            ".application-question label",
            "[data-field-label]",
        ])
        for el in label_els:
            text = (await el.inner_text()).strip()
            if text and text not in ("Resume/CV", "Cover Letter"):
                labels.append(text)
        return labels

    async def fill_form(self, answers: dict[str, str], cv_path: str) -> None:
        for label_text, answer in answers.items():
            try:
                label = await self.page.query_selector(f"label:text-is('{label_text}')")
                if not label:
                    continue
                for_attr = await label.get_attribute("for")
                if for_attr:
                    field = await self.page.query_selector(f"#{for_attr}")
                    if field:
                        from candidatador.applicator.base import _fill_field
                        await _fill_field(field, answer)
                        await asyncio.sleep(0.3)
            except Exception:
                continue
        try:
            file_input = await self.page.query_selector("input[type='file']")
            if file_input and cv_path:
                await file_input.set_input_files(cv_path)
                await asyncio.sleep(1)
        except Exception:
            pass

    async def submit(self) -> str:
        from candidatador.applicator.base import _confirm_submitted
        try:
            submit_btn = await self.page.query_selector("input[type='submit'], button[type='submit']")
            if not submit_btn:
                return "failed"
            await submit_btn.click()
            await self.page.wait_for_load_state("networkidle", timeout=15000)
            return "submitted" if await _confirm_submitted(self.page) else "unverified"
        except Exception:
            return "failed"
