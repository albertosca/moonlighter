import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import TimeoutError as PlaywrightTimeout
from candidatador.applicator.ashby import AshbyApplier


def make_applier(url="https://jobs.ashbyhq.com/openai/123"):
    page = MagicMock()
    page.url = url
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    return AshbyApplier(page, {}, {})


# ── detect() ─────────────────────────────────────────────────────────────────

async def test_detect_ashby_jobs_url():
    applier = make_applier("https://jobs.ashbyhq.com/openai/123")
    assert await applier.detect() is True


async def test_detect_ashbyhq_com_variant():
    applier = make_applier("https://ashbyhq.com/apply/123")
    assert await applier.detect() is True


async def test_detect_non_ashby_url():
    applier = make_applier("https://jobs.lever.co/co/123")
    assert await applier.detect() is False


# ── extract_fields() ──────────────────────────────────────────────────────────

async def test_extract_fields_waits_for_form():
    applier = make_applier()
    applier.page.query_selector_all = AsyncMock(return_value=[])
    await applier.extract_fields()
    applier.page.wait_for_selector.assert_called_once_with("form", timeout=10000)


async def test_extract_fields_timeout_returns_empty():
    applier = make_applier()
    applier.page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeout("timeout"))
    result = await applier.extract_fields()
    assert result == []


async def test_extract_fields_filters_long_labels():
    applier = make_applier()
    long_label = MagicMock()
    long_label.inner_text = AsyncMock(return_value="x" * 201)
    short_label = MagicMock()
    short_label.inner_text = AsyncMock(return_value="Why this role?")
    applier.page.query_selector_all = AsyncMock(return_value=[long_label, short_label])
    result = await applier.extract_fields()
    assert result == ["Why this role?"]


# ── fill_form() ───────────────────────────────────────────────────────────────

async def test_fill_form_fills_inputs():
    applier = make_applier()
    label = MagicMock()
    label.get_attribute = AsyncMock(return_value="why_role")
    field = MagicMock()
    field.fill = AsyncMock()

    async def qs(selector):
        if "label" in selector:
            return label
        return field
    applier.page.query_selector = qs

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Why this role?": "Great company"}, cv_path="")
    field.fill.assert_called_once_with("Great company")


async def test_fill_form_uploads_cv():
    applier = make_applier()
    file_input = MagicMock()
    file_input.set_input_files = AsyncMock()

    async def qs(selector):
        if "file" in selector:
            return file_input
        return None
    applier.page.query_selector = qs

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({}, cv_path="/cv.pdf")
    file_input.set_input_files.assert_called_once_with("/cv.pdf")


# ── submit() ──────────────────────────────────────────────────────────────────

async def test_submit_button_click_returns_true():
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_load_state = AsyncMock()
    assert await applier.submit() is True


async def test_submit_no_button_returns_false():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    assert await applier.submit() is False


async def test_extract_fields_excludes_empty_labels():
    """Labels with empty/whitespace text are excluded."""
    applier = make_applier()
    empty_label = MagicMock()
    empty_label.inner_text = AsyncMock(return_value="   ")
    real_label = MagicMock()
    real_label.inner_text = AsyncMock(return_value="Full Name")
    applier.page.query_selector_all = AsyncMock(return_value=[empty_label, real_label])
    result = await applier.extract_fields()
    assert result == ["Full Name"]


async def test_fill_form_skips_label_without_for_attr():
    """Label with no 'for' attribute → fill never called."""
    applier = make_applier()
    label = MagicMock()
    label.get_attribute = AsyncMock(return_value=None)
    field = MagicMock()
    field.fill = AsyncMock()

    async def qs(selector):
        if "label" in selector:
            return label
        return field
    applier.page.query_selector = qs
    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Q": "A"}, cv_path="")
    field.fill.assert_not_called()


async def test_submit_exception_returns_false():
    """Exception during submit click → returns False."""
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock(side_effect=Exception("crash"))
    applier.page.query_selector = AsyncMock(return_value=btn)
    assert await applier.submit() is False


async def test_extract_fields_falls_back_when_primary_selector_empty():
    """Seletor primário vazio → seletor alternativo tentado."""
    applier = make_applier()

    fallback_label = MagicMock()
    fallback_label.inner_text = AsyncMock(return_value="Why Ashby?")

    call_count = [0]
    async def qs_all(selector):
        call_count[0] += 1
        if call_count[0] == 1:
            return []
        return [fallback_label]

    applier.page.query_selector_all = qs_all
    result = await applier.extract_fields()
    assert "Why Ashby?" in result
    assert call_count[0] >= 2
