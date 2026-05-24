import asyncio
from playwright.async_api import TimeoutError as PlaywrightTimeout
from candidatador.applicator.base import BaseApplier

class AshbyApplier(BaseApplier):
    async def detect(self) -> bool:
        return "ashbyhq.com" in self.page.url or "jobs.ashbyhq.com" in self.page.url

    async def extract_fields(self) -> list[str]:
        try:
            await self.page.wait_for_selector("form", timeout=10000)
        except PlaywrightTimeout:
            return []
        labels = []
        from candidatador.applicator.base import _query_labels_with_fallback
        label_els = await _query_labels_with_fallback(self.page, [
            "label",
            ".ashby-application-form label",
            "[class*='label']:not(legend)",
        ])
        for el in label_els:
            text = (await el.inner_text()).strip()
            if text and len(text) < 200:
                labels.append(text)
        return labels

    async def fill_form(self, answers: dict[str, str], cv_path: str) -> None:
        for label_text, answer in answers.items():
            try:
                label = await self.page.query_selector(f"label:text-is('{label_text}')")
                if not label:
                    continue
                for_id = await label.get_attribute("for")
                if for_id:
                    field = await self.page.query_selector(f"#{for_id}")
                    if field:
                        await field.fill(answer)
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

    async def submit(self) -> bool:
        try:
            btn = await self.page.query_selector("button[type='submit']")
            if btn:
                await btn.click()
                await self.page.wait_for_load_state("networkidle", timeout=15000)
                return True
        except Exception:
            pass
        return False
