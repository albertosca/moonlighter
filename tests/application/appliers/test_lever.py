import logging
from unittest.mock import AsyncMock, MagicMock, patch

from gauntler.application.appliers.lever import LeverApplier
from playwright.async_api import TimeoutError as PlaywrightTimeout


def make_applier(url="https://jobs.lever.co/gitlab/abc-123"):
    page = MagicMock()
    page.url = url
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.inner_text = AsyncMock(return_value="")  # sem confirmação por padrão
    return LeverApplier(page, {}, {})


# ── detect() ─────────────────────────────────────────────────────────────────


async def test_detect_lever_url():
    applier = make_applier("https://jobs.lever.co/gitlab/abc-123")
    assert await applier.detect() is True


async def test_detect_non_lever_url():
    applier = make_applier("https://boards.greenhouse.io/stripe/jobs/1")
    assert await applier.detect() is False


# ── extract_fields() ──────────────────────────────────────────────────────────


async def test_extract_fields_waits_for_application_form():
    applier = make_applier()
    applier.page.query_selector_all = AsyncMock(return_value=[])
    await applier.extract_fields()
    applier.page.wait_for_selector.assert_called_once_with(".application-form", timeout=10000)


async def test_extract_fields_timeout_returns_empty():
    applier = make_applier()
    applier.page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeout("timeout"))
    result = await applier.extract_fields()
    assert result == []


async def test_extract_fields_filters_long_labels():
    """Labels longer than 200 chars are excluded."""
    applier = make_applier()
    long_label = MagicMock()
    long_label.inner_text = AsyncMock(return_value="x" * 201)
    short_label = MagicMock()
    short_label.inner_text = AsyncMock(return_value="Full Name")
    applier.page.query_selector_all = AsyncMock(return_value=[long_label, short_label])
    result = await applier.extract_fields()
    assert result == ["Full Name"]


async def test_extract_fields_excludes_empty_labels():
    applier = make_applier()
    empty_label = MagicMock()
    empty_label.inner_text = AsyncMock(return_value="   ")
    real_label = MagicMock()
    real_label.inner_text = AsyncMock(return_value="Email")
    applier.page.query_selector_all = AsyncMock(return_value=[empty_label, real_label])
    result = await applier.extract_fields()
    assert result == ["Email"]


# ── fill_form() ───────────────────────────────────────────────────────────────


async def test_fill_form_fills_labeled_fields():
    applier = make_applier()
    label = MagicMock()
    label.get_attribute = AsyncMock(return_value="email")
    field = MagicMock()
    field.fill = AsyncMock()
    field.evaluate = AsyncMock(return_value="input")
    field.get_attribute = AsyncMock(return_value="text")

    async def qs(selector):
        if "label" in selector:
            return label
        return field

    applier.page.query_selector = qs

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Email": "a@b.com"}, cv_path="")
    field.fill.assert_called_once_with("a@b.com")


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


async def test_fill_form_skips_sentinel_answers():
    """A sentinel answer (e.g. __NEEDS_REVIEW__) must never be typed into the form.

    field.evaluate/get_attribute are configured (mirroring test_fill_form_fills_labeled_fields)
    so that, absent the skip guard, fill_field would actually run and call field.fill —
    without this, an unconfigured MagicMock.evaluate() raises TypeError on await, which the
    surrounding try/except swallows, making the assertion pass for the wrong reason.
    """
    applier = make_applier()
    label = MagicMock()
    label.get_attribute = AsyncMock(return_value="q1")
    field = MagicMock()
    field.fill = AsyncMock()
    field.evaluate = AsyncMock(return_value="input")
    field.get_attribute = AsyncMock(return_value="text")

    async def qs(selector):
        if "label" in selector:
            return label
        return field

    applier.page.query_selector = qs
    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Q1": "__NEEDS_REVIEW__"}, cv_path="")
    field.fill.assert_not_called()


async def test_fill_form_skips_missing_label():
    """No crash and no fill when label not found."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    await applier.fill_form({"Q": "A"}, cv_path="")  # should not raise


# ── submit() ──────────────────────────────────────────────────────────────────


async def test_submit_clicks_submit_button():
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="Thank you for applying!")
    assert await applier.submit() == "submitted"
    btn.click.assert_called_once()


async def test_submit_template_btn():
    """Template submit button also triggers True return (com confirmação)."""
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="We received your application.")
    assert await applier.submit() == "submitted"


async def test_submit_unverified_without_confirmation():
    """RELIABILITY-01: clicou, sem confirmação E sem form visível → 'unverified'."""
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="Name Email Submit")
    applier.page.evaluate = AsyncMock(return_value=False)  # form não está mais visível
    assert await applier.submit() == "unverified"


async def test_submit_validation_failure_when_form_visible():
    """RELIABILITY: form ainda visível após click → failed:validation_errors (re-tentável)."""
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="sem confirmação")
    applier.page.evaluate = AsyncMock(side_effect=[True, ["Campo obrigatório"]])
    result = await applier.submit()
    assert result.startswith("failed:validation_errors")


async def test_submit_no_button_returns_failed():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    assert await applier.submit() == "failed"


async def test_fill_form_skips_label_without_for_attr():
    """Label with no 'for' attribute → field.fill never called."""
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
    await applier.fill_form({"Q": "A"}, cv_path="")
    field.fill.assert_not_called()


async def test_submit_exception_returns_failed():
    """Exception during click → 'failed'."""
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock(side_effect=Exception("crash"))
    applier.page.query_selector = AsyncMock(return_value=btn)
    assert await applier.submit() == "failed"


async def test_extract_fields_falls_back_when_primary_selector_empty():
    """Seletor primário vazio → seletor alternativo tentado."""
    applier = make_applier()

    fallback_label = MagicMock()
    fallback_label.inner_text = AsyncMock(return_value="LinkedIn Profile")

    call_count = [0]

    async def qs_all(selector):
        call_count[0] += 1
        if call_count[0] == 1:
            return []
        return [fallback_label]

    applier.page.query_selector_all = qs_all
    result = await applier.extract_fields()
    assert "LinkedIn Profile" in result
    assert call_count[0] >= 2


# ── fill_form: branches de borda ───────────────────────────────────────────


async def test_fill_form_skips_when_field_missing():
    """label com for=fid mas #fid não existe → campo não preenchido (43->loop)."""
    applier = make_applier()
    label = MagicMock()
    label.get_attribute = AsyncMock(return_value="fid")

    async def qs(selector):
        return label if "label" in selector else None

    applier.page.query_selector = qs
    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Q": "A"}, cv_path="")


async def test_fill_form_swallows_exceptions(caplog):
    """query_selector raises throughout the flow -> both the field loop and the CV
    upload swallow the exception, and both log it at debug level."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(side_effect=Exception("boom"))
    with (
        patch("asyncio.sleep", new=AsyncMock()),
        caplog.at_level(logging.DEBUG, logger="gauntler.application.appliers.lever"),
    ):
        await applier.fill_form({"Q": "A"}, cv_path="/cv.pdf")
    assert "skipping field 'Q'" in caplog.text
    assert "CV upload failed" in caplog.text
