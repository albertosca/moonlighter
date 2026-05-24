import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import TimeoutError as PlaywrightTimeout
from candidatador.applicator.greenhouse import GreenhouseApplier


def make_applier(url="https://boards.greenhouse.io/stripe/jobs/123"):
    page = MagicMock()
    page.url = url
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_load_state = AsyncMock()
    config = {}
    profile = {}
    return GreenhouseApplier(page, config, profile)


# ── detect() ─────────────────────────────────────────────────────────────────

async def test_detect_greenhouse_board_url():
    applier = make_applier("https://boards.greenhouse.io/stripe/jobs/123")
    assert await applier.detect() is True


async def test_detect_greenhouse_io_url():
    applier = make_applier("https://stripe.greenhouse.io/apply")
    assert await applier.detect() is True


async def test_detect_non_greenhouse_url():
    applier = make_applier("https://jobs.lever.co/stripe/123")
    assert await applier.detect() is False


async def test_detect_unrelated_url():
    applier = make_applier("https://example.com/careers")
    assert await applier.detect() is False


# ── extract_fields() ──────────────────────────────────────────────────────────

async def test_extract_fields_with_apply_button():
    """When apply button exists, it is clicked before extracting labels."""
    applier = make_applier()
    apply_btn = AsyncMock()
    apply_btn.click = AsyncMock()

    # query_selector returns the apply button for the first call, then None for each label
    call_count = [0]
    async def query_selector_side_effect(selector):
        call_count[0] += 1
        if call_count[0] == 1:
            return apply_btn
        return None
    applier.page.query_selector = query_selector_side_effect
    applier.page.query_selector_all = AsyncMock(return_value=[])

    await applier.extract_fields()
    apply_btn.click.assert_called_once()


async def test_extract_fields_no_apply_button():
    """When no apply button, extraction proceeds without clicking."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    label_mock = MagicMock()
    label_mock.inner_text = AsyncMock(return_value="Full Name")
    applier.page.query_selector_all = AsyncMock(return_value=[label_mock])

    fields = await applier.extract_fields()
    assert "Full Name" in fields


async def test_extract_fields_excludes_resume_cv():
    """'Resume/CV' label is excluded from results."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    label_mock = MagicMock()
    label_mock.inner_text = AsyncMock(return_value="Resume/CV")
    applier.page.query_selector_all = AsyncMock(return_value=[label_mock])

    fields = await applier.extract_fields()
    assert "Resume/CV" not in fields


async def test_extract_fields_excludes_cover_letter():
    """'Cover Letter' label is excluded from results."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    label_mock = MagicMock()
    label_mock.inner_text = AsyncMock(return_value="Cover Letter")
    applier.page.query_selector_all = AsyncMock(return_value=[label_mock])

    fields = await applier.extract_fields()
    assert "Cover Letter" not in fields


async def test_extract_fields_returns_non_empty_labels():
    """Only non-empty label texts are returned."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    labels = []
    for text in ["Full Name", "", "Email Address"]:
        m = MagicMock()
        m.inner_text = AsyncMock(return_value=text)
        labels.append(m)
    applier.page.query_selector_all = AsyncMock(return_value=labels)

    fields = await applier.extract_fields()
    assert fields == ["Full Name", "Email Address"]


async def test_extract_fields_timeout_on_load_state():
    """PlaywrightTimeout after clicking apply button doesn't crash; extraction continues."""
    applier = make_applier()
    apply_btn = AsyncMock()
    apply_btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=apply_btn)
    applier.page.wait_for_load_state = AsyncMock(side_effect=PlaywrightTimeout("timeout"))
    label_mock = MagicMock()
    label_mock.inner_text = AsyncMock(return_value="Full Name")
    applier.page.query_selector_all = AsyncMock(return_value=[label_mock])

    fields = await applier.extract_fields()
    assert "Full Name" in fields


# ── fill_form() ───────────────────────────────────────────────────────────────

async def test_fill_form_fills_text_inputs():
    """fill() is called on input fields associated with labels."""
    applier = make_applier()

    label = MagicMock()
    label.get_attribute = AsyncMock(return_value="full_name")

    field = MagicMock()
    field.evaluate = AsyncMock(return_value="input")
    field.fill = AsyncMock()

    async def query_selector_side(selector):
        if "label" in selector:
            return label
        return field
    applier.page.query_selector = query_selector_side

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Full Name": "Alberto"}, cv_path="")

    field.fill.assert_called_once_with("Alberto")


async def test_fill_form_fills_textareas():
    """fill() is also called on textarea fields."""
    applier = make_applier()

    label = MagicMock()
    label.get_attribute = AsyncMock(return_value="bio")

    field = MagicMock()
    field.evaluate = AsyncMock(return_value="textarea")
    field.fill = AsyncMock()

    async def query_selector_side(selector):
        if "label" in selector:
            return label
        return field
    applier.page.query_selector = query_selector_side

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Bio": "Senior engineer"}, cv_path="")

    field.fill.assert_called_once_with("Senior engineer")


async def test_fill_form_skips_label_without_for_attr():
    """If label has no 'for' attribute, no field is filled."""
    applier = make_applier()

    label = MagicMock()
    label.get_attribute = AsyncMock(return_value=None)  # no for attr

    field = MagicMock()
    field.fill = AsyncMock()

    async def query_selector_side(selector):
        if "label" in selector:
            return label
        return field
    applier.page.query_selector = query_selector_side

    await applier.fill_form({"Full Name": "Alberto"}, cv_path="")
    field.fill.assert_not_called()


async def test_fill_form_uploads_cv():
    """file input has set_input_files called with cv_path."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)  # no labels

    file_input = MagicMock()
    file_input.set_input_files = AsyncMock()

    # Second call for file input
    call_count = [0]
    async def query_selector_side(selector):
        call_count[0] += 1
        if "file" in selector:
            return file_input
        return None
    applier.page.query_selector = query_selector_side

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({}, cv_path="/path/to/cv.pdf")

    file_input.set_input_files.assert_called_once_with("/path/to/cv.pdf")


async def test_fill_form_skips_cv_if_no_file_input():
    """If no file input exists, no crash occurs."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    # Should not raise
    await applier.fill_form({}, cv_path="/path/to/cv.pdf")


async def test_fill_form_exception_in_field_continues():
    """Exception in one field fill does not prevent other fields from being filled."""
    applier = make_applier()

    fill_calls = []

    async def query_selector_side(selector):
        if "label:text-is('Field1')" in selector:
            raise Exception("element not found")
        if "label:text-is('Field2')" in selector:
            label = MagicMock()
            label.get_attribute = AsyncMock(return_value="field2")
            return label
        if selector == "#field2":
            field = MagicMock()
            field.evaluate = AsyncMock(return_value="input")
            async def do_fill(val):
                fill_calls.append(val)
            field.fill = do_fill
            return field
        return None

    applier.page.query_selector = query_selector_side

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Field1": "val1", "Field2": "val2"}, cv_path="")

    assert "val2" in fill_calls


# ── submit() ──────────────────────────────────────────────────────────────────

async def test_submit_clicks_submit_button():
    """submit() clicks submit button and returns True."""
    applier = make_applier()

    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_load_state = AsyncMock()

    result = await applier.submit()
    assert result is True
    btn.click.assert_called_once()


async def test_submit_no_button_returns_false():
    """submit() returns False when no submit button found."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    result = await applier.submit()
    assert result is False


async def test_submit_exception_returns_false():
    """submit() returns False when click raises an exception."""
    applier = make_applier()

    btn = MagicMock()
    btn.click = AsyncMock(side_effect=Exception("click failed"))
    applier.page.query_selector = AsyncMock(return_value=btn)

    result = await applier.submit()
    assert result is False


async def test_extract_fields_falls_back_when_primary_selector_empty():
    """Quando seletor primário retorna vazio, seletor alternativo é tentado."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    fallback_label = MagicMock()
    fallback_label.inner_text = AsyncMock(return_value="Portfolio URL")

    call_count = [0]
    async def qs_all(selector):
        call_count[0] += 1
        if call_count[0] == 1:
            return []  # primeiro seletor vazio
        return [fallback_label]  # fallback retorna label

    applier.page.query_selector_all = qs_all
    fields = await applier.extract_fields()
    assert "Portfolio URL" in fields
    assert call_count[0] >= 2  # tentou mais de um seletor
