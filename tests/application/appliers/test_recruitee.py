import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.application.appliers.recruitee import RecruiteeApplier
from playwright.async_api import TimeoutError as PlaywrightTimeout


def make_label_locator(field_mock=None):
    """Creates a mock Playwright Locator that returns field_mock via element_handle()."""
    locator = MagicMock()
    locator.count = AsyncMock(return_value=1 if field_mock else 0)
    locator.first = MagicMock()
    locator.first.element_handle = AsyncMock(return_value=field_mock)
    return locator


def make_applier(url="https://acme.recruitee.com/o/backend-engineer"):
    page = MagicMock()
    page.url = url
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_load_state = AsyncMock()
    page.inner_text = AsyncMock(return_value="")  # no confirmation by default
    page.get_by_label = MagicMock(return_value=make_label_locator(None))  # default: no match
    page.evaluate = AsyncMock(return_value=None)
    config = {}
    profile = {}
    return RecruiteeApplier(page, config, profile)


def make_evaluate(tag, combobox=False, selected=""):
    """Stub of field.evaluate robust to call order/count: returns the selected
    value (single-value), the combobox flag, and the tag according to the JS called."""

    async def _ev(js, *args):
        if "single-value" in js:
            return selected
        if "aria-haspopup" in js or "combobox" in js or "select__input" in js:
            return combobox
        if "tagName" in js:
            return tag
        return None

    return _ev


# ── detect() ─────────────────────────────────────────────────────────────────


async def test_detect_recruitee_url():
    applier = make_applier("https://acme.recruitee.com/o/backend-engineer")
    assert await applier.detect() is True


async def test_detect_non_recruitee_url():
    applier = make_applier("https://jobs.lever.co/stripe/123")
    assert await applier.detect() is False


async def test_detect_unrelated_url():
    applier = make_applier("https://example.com/careers")
    assert await applier.detect() is False


@pytest.mark.asyncio
async def test_recruitee_detect_logs_match(caplog):
    applier = make_applier("https://acme.recruitee.com/o/backend-engineer")
    with caplog.at_level(logging.DEBUG, logger="moonlighter.application.appliers.recruitee"):
        await applier.detect()
    assert "detect: recruitee" in caplog.text


# ── extract_fields() ──────────────────────────────────────────────────────────


async def test_extract_fields_with_apply_button():
    """When apply button exists, it is clicked before extracting labels."""
    applier = make_applier()
    apply_btn = AsyncMock()
    apply_btn.click = AsyncMock()

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


async def test_open_application_selector_matches_live_recruitee_apply_button():
    """LIVE-VERIFY confirmed (Ziflow, a real *.recruitee.com posting): the actual
    'Apply' CTA carries data-cy='apply-button', not any of the previously guessed
    selectors (a#apply-button, button#apply-button, a[href='#apply'],
    button[data-testid='apply-button']) — none of those matched and the form
    stayed collapsed/hidden, so every text field failed to fill with
    'element is not visible'. The selector query must include the confirmed one."""
    applier = make_applier()
    captured_selector = None

    async def query_selector_side_effect(selector):
        nonlocal captured_selector
        captured_selector = selector
        return

    applier.page.query_selector = query_selector_side_effect
    await applier.extract_fields()
    assert "[data-cy='apply-button']" in captured_selector


async def test_extract_fields_no_apply_button():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    label_mock = MagicMock()
    label_mock.inner_text = AsyncMock(return_value="Full Name")
    applier.page.query_selector_all = AsyncMock(return_value=[label_mock])

    fields, _ = await applier.extract_fields()
    assert "Full Name" in fields


async def test_extract_fields_excludes_resume_cv():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    label_mock = MagicMock()
    label_mock.inner_text = AsyncMock(return_value="Resume/CV")
    applier.page.query_selector_all = AsyncMock(return_value=[label_mock])

    fields, _ = await applier.extract_fields()
    assert "Resume/CV" not in fields


async def test_extract_fields_returns_non_empty_labels():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    labels = []
    for text in ["Full Name", "", "Email Address"]:
        m = MagicMock()
        m.inner_text = AsyncMock(return_value=text)
        labels.append(m)
    applier.page.query_selector_all = AsyncMock(return_value=labels)

    fields, _ = await applier.extract_fields()
    assert fields == ["Full Name", "Email Address"]


async def test_extract_fields_reports_closed_set_labels():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    select_label = MagicMock()
    select_label.inner_text = AsyncMock(return_value="English level")
    select_label.evaluate = AsyncMock(return_value=True)

    text_label = MagicMock()
    text_label.inner_text = AsyncMock(return_value="Full name")
    text_label.evaluate = AsyncMock(return_value=False)

    applier.page.query_selector_all = AsyncMock(return_value=[select_label, text_label])

    fields, closed_set = await applier.extract_fields()
    assert fields == ["English level", "Full name"]
    assert closed_set == frozenset({"English level"})


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

    fields, _ = await applier.extract_fields()
    assert "Full Name" in fields


async def test_extract_fields_falls_back_when_primary_selector_empty():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    fallback_label = MagicMock()
    fallback_label.inner_text = AsyncMock(return_value="Portfolio URL")

    call_count = [0]

    async def qs_all(selector):
        call_count[0] += 1
        if call_count[0] == 1:
            return []
        return [fallback_label]

    applier.page.query_selector_all = qs_all
    fields, _ = await applier.extract_fields()
    assert "Portfolio URL" in fields
    assert call_count[0] >= 2


# ── fill_form() ───────────────────────────────────────────────────────────────


async def test_fill_form_fills_text_inputs():
    applier = make_applier()

    field = MagicMock()
    field.evaluate = make_evaluate("input")
    field.get_attribute = AsyncMock(return_value="text")
    field.fill = AsyncMock()

    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Full Name": "Alberto"}, cv_path="")

    field.fill.assert_called_once_with("Alberto")


async def test_fill_form_selects_dropdown_option():
    """A <select> field is resolved via select_option (by label), not fill."""
    applier = make_applier()

    field = MagicMock()
    field.evaluate = make_evaluate("select")
    field.fill = AsyncMock()
    field.select_option = AsyncMock()

    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Authorized to work?": "Yes"}, cv_path="")

    field.select_option.assert_called_once_with(label="Yes")
    field.fill.assert_not_called()


async def test_fill_form_skips_empty_answer():
    applier = make_applier()
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"Field": ""}, cv_path="")
    assert result.get("Field") == "skipped"


async def test_fill_form_skips_skip_sentinel():
    applier = make_applier()
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"Attach": "__SKIP__"}, cv_path="")
    assert result.get("Attach") == "skipped"


async def test_fill_form_marks_failed_when_field_not_found():
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value=None)
    applier.page.query_selector = AsyncMock(return_value=None)
    applier.page.locator = MagicMock(
        return_value=MagicMock(first=MagicMock(count=AsyncMock(return_value=0)))
    )

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"Nonexistent Field": "value"}, cv_path="")

    assert result.get("Nonexistent Field") == "failed:not_found"


async def test_fill_form_exception_in_field_continues():
    applier = make_applier()

    fill_calls = []

    field2 = MagicMock()
    field2.evaluate = make_evaluate("input")
    field2.get_attribute = AsyncMock(return_value="text")

    async def do_fill(val):
        fill_calls.append(val)

    field2.fill = do_fill

    def get_by_label_side(text, exact=True):
        if "Field1" in text:
            loc = MagicMock()
            loc.count = AsyncMock(return_value=1)
            loc.first = MagicMock()
            loc.first.element_handle = AsyncMock(side_effect=Exception("field1 broke"))
            return loc
        if "Field2" in text:
            return make_label_locator(field2)
        return make_label_locator(None)

    applier.page.get_by_label = get_by_label_side

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Field1": "val1", "Field2": "val2"}, cv_path="")

    assert "val2" in fill_calls


async def test_fill_form_routes_combobox_input_to_custom_dropdown():
    """A react-select-style <input role=combobox> must go to the custom dropdown
    handler via CustomDropdownFiller, not be treated as a text input."""
    applier = make_applier()
    field = MagicMock()
    field.evaluate = make_evaluate("input", combobox=True)
    field.fill = AsyncMock()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))
    applier._dropdown.select_custom_option = AsyncMock(return_value=True)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"How did you hear about us?": "LinkedIn"}, cv_path="")

    assert result["How did you hear about us?"] == "filled"
    applier._dropdown.select_custom_option.assert_awaited_once()
    field.fill.assert_not_called()


async def test_fill_form_combobox_no_match_marks_failed_not_filled():
    applier = make_applier()
    field = MagicMock()
    field.evaluate = make_evaluate("input", combobox=True)
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))
    applier._dropdown.select_custom_option = AsyncMock(return_value=False)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"English level": "Fluent"}, cv_path="")

    assert result["English level"] == "failed:custom_dropdown"


async def test_fill_form_routes_non_native_element_to_custom():
    applier = make_applier()
    field = MagicMock()

    async def ev(js, *a):
        if "combobox" in js or "aria-haspopup" in js or "select__input" in js:
            return False
        if "tagName" in js:
            return "div"
        return None

    field.evaluate = ev
    applier._find_field = AsyncMock(return_value=field)
    applier._dropdown.fill_custom_element = AsyncMock(return_value=True)
    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({"Q": "A"}, cv_path="")
    assert status["Q"] == "filled"


async def test_fill_form_uploads_cv():
    applier = make_applier()

    file_locator_first = MagicMock()
    file_locator_first.count = AsyncMock(return_value=1)
    file_locator_first.set_input_files = AsyncMock()
    file_locator = MagicMock()
    file_locator.first = file_locator_first
    applier.page.locator = MagicMock(return_value=file_locator)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({}, cv_path="/path/to/cv.pdf")

    file_locator_first.set_input_files.assert_called_once_with("/path/to/cv.pdf")
    assert result.get("__cv__") == "filled"


# ── _upload_cv() ──────────────────────────────────────────────────────────────


async def test_upload_cv_skips_when_no_path():
    applier = make_applier()
    result = await applier._upload_cv("")
    assert result == "skipped"


async def test_upload_cv_falls_back_to_query_selector():
    applier = make_applier()
    file_input = MagicMock()
    file_input.set_input_files = AsyncMock()

    empty_first = MagicMock()
    empty_first.count = AsyncMock(return_value=0)
    applier.page.locator = MagicMock(return_value=MagicMock(first=empty_first))
    applier.page.query_selector = AsyncMock(return_value=file_input)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._upload_cv("/path/cv.pdf")

    assert result == "filled"
    file_input.set_input_files.assert_called_once_with("/path/cv.pdf")


async def test_upload_cv_returns_failed_when_no_input_found():
    applier = make_applier()
    empty_first = MagicMock()
    empty_first.count = AsyncMock(return_value=0)
    applier.page.locator = MagicMock(return_value=MagicMock(first=empty_first))
    applier.page.query_selector = AsyncMock(return_value=None)

    result = await applier._upload_cv("/path/cv.pdf")
    assert result == "failed:no_file_input"


async def test_upload_cv_exception_returns_failed(caplog):
    applier = make_applier()
    applier.page.locator = MagicMock(side_effect=Exception("boom"))

    result = await applier._upload_cv("/path/cv.pdf")
    assert result == "failed:Exception"


# ── _find_field() ─────────────────────────────────────────────────────────────


async def test_find_field_uses_get_by_label_exact_first():
    applier = make_applier()
    field = MagicMock()
    field.evaluate = make_evaluate("input")
    exact_locator = make_label_locator(field)
    call_args = []

    def get_by_label(text, exact=True):
        call_args.append(exact)
        return exact_locator

    applier.page.get_by_label = get_by_label
    result = await applier._find_field("First Name")
    assert result is field
    assert call_args[0] is True


async def test_find_field_falls_back_to_inexact():
    applier = make_applier()
    field = MagicMock()
    inexact_locator = make_label_locator(field)
    empty_locator = make_label_locator(None)

    def get_by_label(text, exact=True):
        return empty_locator if exact else inexact_locator

    applier.page.get_by_label = get_by_label
    result = await applier._find_field("First Name")
    assert result is field


async def test_find_field_js_fallback_uses_for_attribute():
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value="phone_field")
    field = MagicMock()
    applier.page.query_selector = AsyncMock(return_value=field)

    result = await applier._find_field("Phone")
    assert result is field
    applier.page.query_selector.assert_called_once_with("#phone_field")


async def test_find_field_for_id_missing_falls_to_aria():
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value="phone_field")
    aria_field = MagicMock()

    async def qs(selector):
        if selector == "#phone_field":
            return None
        if "aria-label" in selector:
            return aria_field
        return None

    applier.page.query_selector = qs
    result = await applier._find_field("Phone")
    assert result is aria_field


async def test_find_field_aria_label_strategy():
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value=None)
    field = MagicMock()

    call_count = [0]

    async def qs_side(selector):
        call_count[0] += 1
        if "aria-label" in selector:
            return field
        return None

    applier.page.query_selector = qs_side

    result = await applier._find_field("Phone Number")
    assert result is field


async def test_find_field_returns_none_when_all_fail():
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value=None)
    applier.page.query_selector = AsyncMock(return_value=None)

    result = await applier._find_field("Unknown Label XYZ")
    assert result is None


# ── submit() ──────────────────────────────────────────────────────────────────


async def test_submit_returns_submitted_on_confirmation():
    applier = make_applier()

    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(
        return_value="Thank you for applying! Application submitted."
    )

    result = await applier.submit()
    assert result == "submitted"
    btn.click.assert_called_once()


async def test_submit_unverified_without_confirmation():
    applier = make_applier("https://acme.recruitee.com/o/backend-engineer")

    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="Full Name Email Submit Application")

    result = await applier.submit()
    assert result == "unverified"


async def test_submit_no_button_returns_failed():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    result = await applier.submit()
    assert result == "failed"


async def test_submit_exception_returns_failed():
    applier = make_applier()

    btn = MagicMock()
    btn.click = AsyncMock(side_effect=Exception("click failed"))
    applier.page.query_selector = AsyncMock(return_value=btn)

    result = await applier.submit()
    assert result == "failed"


async def test_submit_logs_empty_required_fields(caplog):
    """submit() logs a warning when required fields are empty before submitting.
    Mirrors greenhouse's _empty_required_fields check — Recruitee's submit()
    used to go straight to the click with no such warning."""
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="thank you for applying")
    applier.page.query_selector = AsyncMock(return_value=btn)
    # evaluate: (1) empty required fields present, (2) form not visible after submit
    applier.page.evaluate = AsyncMock(side_effect=[["Full name *"], False, []])

    with caplog.at_level(logging.WARNING, logger="moonlighter.application.appliers.recruitee"):
        await applier.submit()

    assert "Full name" in caplog.text


async def test_submit_detects_form_still_visible_after_click():
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="some page without confirmation")
    applier.page.url = "https://acme.recruitee.com/o/backend-engineer"

    call_n = [0]

    async def qs_side(selector):
        call_n[0] += 1
        if "submit" in selector and call_n[0] == 1:
            return btn
        return None

    applier.page.query_selector = qs_side

    eval_calls = [[], True, []]
    eval_n = [0]

    async def eval_side(js, *args):
        result = eval_calls[eval_n[0]]
        eval_n[0] = min(eval_n[0] + 1, len(eval_calls) - 1)
        return result

    applier.page.evaluate = eval_side

    result = await applier.submit()
    assert result.startswith("failed:validation_errors")


@pytest.mark.asyncio
async def test_recruitee_submit_logs_outcome(caplog):
    applier = make_applier("https://acme.recruitee.com/o/backend-engineer")
    submit_btn = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=submit_btn)
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="application submitted successfully")
    applier.page.url = "https://acme.recruitee.com/confirmation"

    with caplog.at_level(logging.INFO, logger="moonlighter.application.appliers.recruitee"):
        outcome = await applier.submit()

    assert "submit" in caplog.text
    assert outcome in ("submitted", "unverified")
