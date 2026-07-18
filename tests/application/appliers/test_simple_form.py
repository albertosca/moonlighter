from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

from gauntler.application.appliers.simple_form import SimpleFormApplier


class _Demo(SimpleFormApplier):
    URL_HOSTS = ("demo.test",)
    FORM_SELECTOR = "form"
    LABEL_SELECTORS: ClassVar[list[str]] = ["label"]
    SUBMIT_SELECTOR = "button[type='submit']"


def _applier(url="https://demo.test/apply"):
    page = MagicMock()
    page.url = url
    page.query_selector = AsyncMock(return_value=None)
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.inner_text = AsyncMock(return_value="")
    return _Demo(page, {}, {})


async def test_detect_matches_host():
    assert await _applier().detect() is True
    assert await _applier("https://other.test/x").detect() is False


async def test_fill_form_status_filled_and_skipped():
    applier = _applier()
    label = MagicMock()
    label.get_attribute = AsyncMock(return_value="fld")
    field = MagicMock()
    field.fill = AsyncMock()
    field.evaluate = AsyncMock(return_value="input")
    field.get_attribute = AsyncMock(return_value="text")

    async def qs(sel):
        return label if "label" in sel else field

    applier.page.query_selector = qs
    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({"Name": "Bob", "Secret": "__NEEDS_REVIEW__"}, cv_path="")
    assert status["Name"] == "filled"
    assert status["Secret"] == "skipped"


async def test_fill_form_field_not_found_is_surfaced_not_silent():
    applier = _applier()
    applier.page.query_selector = AsyncMock(return_value=None)  # no label/field
    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({"Q": "A"}, cv_path="")
    assert status["Q"] == "failed:not_found"  # S-12: must be visible, not dropped


async def test_fill_form_field_raises_is_surfaced():
    applier = _applier()
    applier.page.query_selector = AsyncMock(side_effect=Exception("boom"))
    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({"Q": "A"}, cv_path="")
    assert status["Q"] == "failed:Exception"


async def test_fill_form_cv_upload_status():
    applier = _applier()
    file_input = MagicMock()
    file_input.set_input_files = AsyncMock()

    async def qs(sel):
        return file_input if "file" in sel else None

    applier.page.query_selector = qs
    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({}, cv_path="/cv.pdf")
    assert status["__cv__"] == "filled"


async def test_fill_form_cv_upload_not_found():
    applier = _applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({}, cv_path="/cv.pdf")
    assert status["__cv__"] == "failed:not_found"


async def test_fill_form_no_cv_path_omits_cv_key():
    applier = _applier()
    status = await applier.fill_form({}, cv_path="")
    assert "__cv__" not in status
