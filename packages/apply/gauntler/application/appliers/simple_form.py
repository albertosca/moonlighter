import asyncio
from typing import ClassVar

from gauntler.application.appliers.base import (
    BaseApplier,
    classify_submit_outcome,
    fill_field,
    is_skip,
    query_labels_with_fallback,
)
from gauntler.core.log import get_logger
from playwright.async_api import TimeoutError as PlaywrightTimeout

logger = get_logger(__name__)


class SimpleFormApplier(BaseApplier):
    """Shared machinery for simple native-field ATS forms (lever, ashby). Subclasses set
    the four selector attributes; all fill/upload/submit logic is inherited. fill_form
    returns a per-field status dict (label -> "filled"|"skipped"|"failed:<reason>", plus
    "__cv__") so partial fill failures surface instead of silently reaching submit (S-12)."""

    URL_HOSTS: ClassVar[tuple[str, ...]] = ()
    FORM_SELECTOR: str = "form"
    LABEL_SELECTORS: ClassVar[list[str]] = ["label"]
    SUBMIT_SELECTOR: str = "button[type='submit']"

    async def detect(self) -> bool:
        return any(host in self.page.url for host in self.URL_HOSTS)

    async def extract_fields(self) -> list[str]:
        try:
            await self.page.wait_for_selector(self.FORM_SELECTOR, timeout=10000)
        except PlaywrightTimeout:
            return []
        labels: list[str] = []
        for el in await query_labels_with_fallback(self.page, self.LABEL_SELECTORS):
            text = (await el.inner_text()).strip()
            if text and len(text) < 200:
                labels.append(text)
        return labels

    async def fill_form(self, answers: dict[str, str], cv_path: str) -> dict[str, str]:
        status = {label: await self._fill_one(label, answer) for label, answer in answers.items()}
        if cv_path:
            status["__cv__"] = await self._upload_cv(cv_path)
        return status

    async def _fill_one(self, label_text: str, answer: str) -> str:
        if is_skip(answer):
            return "skipped"
        try:
            label = await self.page.query_selector(f"label:text-is('{label_text}')")
            if not label:
                return "failed:not_found"
            for_id = await label.get_attribute("for")
            if not for_id:
                return "failed:not_found"
            field = await self.page.query_selector(f"#{for_id}")
            if not field:
                return "failed:not_found"
            await fill_field(field, answer)
            await asyncio.sleep(0.3)
            return "filled"
        except Exception as e:
            logger.debug("fill failed for %r: %s", label_text, e)
            return f"failed:{type(e).__name__}"

    async def _upload_cv(self, cv_path: str) -> str:
        try:
            file_input = await self.page.query_selector("input[type='file']")
            if file_input:
                await file_input.set_input_files(cv_path)
                await asyncio.sleep(1)
                return "filled"
            return "failed:not_found"
        except Exception as e:
            logger.debug("CV upload failed: %s", e)
            return f"failed:{type(e).__name__}"

    async def submit(self) -> str:
        try:
            btn = await self.page.query_selector(self.SUBMIT_SELECTOR)
            if not btn:
                return "failed"
            await btn.click()
            await self.page.wait_for_load_state("networkidle", timeout=15000)
            return await classify_submit_outcome(self.page)
        except Exception:
            return "failed"
