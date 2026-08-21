import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.application.appliers.greenhouse import GreenhouseApplier
from playwright.async_api import TimeoutError as PlaywrightTimeout


def make_label_locator(field_mock=None):
    """Creates a mock Playwright Locator that returns field_mock via element_handle()."""
    locator = MagicMock()
    locator.count = AsyncMock(return_value=1 if field_mock else 0)
    locator.first = MagicMock()
    locator.first.element_handle = AsyncMock(return_value=field_mock)
    return locator


def make_applier(url="https://boards.greenhouse.io/stripe/jobs/123"):
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
    return GreenhouseApplier(page, config, profile)


# ── BaseApplier capability-hook defaults (no-op, exercised via a concrete
# subclass that doesn't override them) ───────────────────────────────────────


async def test_not_applicable_reason_defaults_to_none():
    applier = make_applier()
    assert await applier.not_applicable_reason() is None


async def test_prepare_defaults_to_noop():
    applier = make_applier()
    assert await applier.prepare() is None


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

    fields, _ = await applier.extract_fields()
    assert "Full Name" in fields


async def test_extract_fields_excludes_resume_cv():
    """'Resume/CV' label is excluded from results."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    label_mock = MagicMock()
    label_mock.inner_text = AsyncMock(return_value="Resume/CV")
    applier.page.query_selector_all = AsyncMock(return_value=[label_mock])

    fields, _ = await applier.extract_fields()
    assert "Resume/CV" not in fields


async def test_extract_fields_excludes_cover_letter():
    """'Cover Letter' label is excluded from results."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    label_mock = MagicMock()
    label_mock.inner_text = AsyncMock(return_value="Cover Letter")
    applier.page.query_selector_all = AsyncMock(return_value=[label_mock])

    fields, _ = await applier.extract_fields()
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

    fields, _ = await applier.extract_fields()
    assert fields == ["Full Name", "Email Address"]


async def test_extract_fields_reports_closed_set_labels():
    """A label whose control is closed-set (select/radio/checkbox) lands in
    the returned closed_set frozenset; a plain text-input label does not."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    select_label = MagicMock()
    select_label.inner_text = AsyncMock(return_value="English level")
    select_label.evaluate = AsyncMock(return_value=True)

    text_label = MagicMock()
    text_label.inner_text = AsyncMock(return_value="Full Name")
    text_label.evaluate = AsyncMock(return_value=False)

    applier.page.query_selector_all = AsyncMock(return_value=[select_label, text_label])

    fields, closed_set = await applier.extract_fields()
    assert fields == ["English level", "Full Name"]
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


# ── fill_form() ───────────────────────────────────────────────────────────────


async def test_fill_form_fills_text_inputs():
    """fill() is called via get_by_label (strategy 1)."""
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
    """QUALITY-02: a <select> field is resolved via select_option (by label), not fill."""
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


async def test_fill_form_fills_textareas():
    """fill() is called on textarea fields via get_by_label."""
    applier = make_applier()

    field = MagicMock()
    field.evaluate = make_evaluate("textarea")
    field.fill = AsyncMock()

    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Bio": "Senior engineer"}, cv_path="")

    field.fill.assert_called_once_with("Senior engineer")


async def test_fill_form_skips_when_no_field_found():
    """If get_by_label and the JS fallback don't find the field, no fill is called."""
    applier = make_applier()
    # get_by_label returns a locator with no match (already make_applier's default)
    # evaluate returns None (no for_id) — already the default

    field = MagicMock()
    field.fill = AsyncMock()

    await applier.fill_form({"Full Name": "Alberto"}, cv_path="")
    field.fill.assert_not_called()


async def test_fill_form_uploads_cv():
    """set_input_files is called on the file input locator with cv_path."""
    applier = make_applier()

    file_input = MagicMock()
    file_input.set_input_files = AsyncMock()

    # Mocka page.locator("input[type='file']").first
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


async def test_fill_form_skips_cv_if_no_file_input():
    """If no file input exists, no crash occurs."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    # Should not raise
    await applier.fill_form({}, cv_path="/path/to/cv.pdf")


async def test_fill_form_exception_in_field_continues():
    """An exception on one field does not prevent the others from being filled."""
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
            # Locator que levanta exception no element_handle
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


# ── submit() ──────────────────────────────────────────────────────────────────


async def test_submit_returns_submitted_on_confirmation():
    """submit() → 'submitted' when the page confirms the submission."""
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
    """RELIABILITY-01: clicked but with no confirmation marker → 'unverified'."""
    applier = make_applier("https://boards.greenhouse.io/stripe/jobs/123")

    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="Full Name Email Submit Application")

    result = await applier.submit()
    assert result == "unverified"


async def test_submit_no_button_returns_failed():
    """submit() → 'failed' when it can't find the submit button."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    result = await applier.submit()
    assert result == "failed"


async def test_submit_exception_returns_failed():
    """submit() → 'failed' when the click raises an exception."""
    applier = make_applier()

    btn = MagicMock()
    btn.click = AsyncMock(side_effect=Exception("click failed"))
    applier.page.query_selector = AsyncMock(return_value=btn)

    result = await applier.submit()
    assert result == "failed"


async def test_extract_fields_falls_back_when_primary_selector_empty():
    """When the primary selector returns empty, the alternative selector is tried."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    fallback_label = MagicMock()
    fallback_label.inner_text = AsyncMock(return_value="Portfolio URL")

    call_count = [0]

    async def qs_all(selector):
        call_count[0] += 1
        if call_count[0] == 1:
            return []  # first selector empty
        return [fallback_label]  # fallback retorna label

    applier.page.query_selector_all = qs_all
    fields, _ = await applier.extract_fields()
    assert "Portfolio URL" in fields
    assert call_count[0] >= 2  # tentou mais de um seletor


# ── _find_field() ─────────────────────────────────────────────────────────────


async def test_find_field_uses_get_by_label_exact_first():
    """_find_field tries get_by_label exact=True before exact=False."""
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
    assert call_args[0] is True  # tried exact first


async def test_find_field_falls_back_to_inexact():
    """_find_field uses exact=False when exact=True finds nothing."""
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
    """_find_field uses JS to normalize the label and look up by for-id when get_by_label fails."""
    applier = make_applier()
    # get_by_label finds nothing
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    # JS returns a for_id
    applier.page.evaluate = AsyncMock(return_value="phone_field")
    field = MagicMock()
    applier.page.query_selector = AsyncMock(return_value=field)

    result = await applier._find_field("Phone")
    assert result is field
    applier.page.query_selector.assert_called_once_with("#phone_field")


async def test_find_field_falls_back_to_the_labeled_input_lookup():
    """Last resort: match on aria-label. The label is compared normalised inside
    the page rather than spliced into a CSS selector — a label with a newline
    made that selector raise BADSTRING, surfacing as failed:Error."""
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value=None)
    applier.page.query_selector = AsyncMock(return_value=None)
    field = MagicMock()

    with patch(
        "moonlighter.application.appliers.greenhouse.find_labeled_input",
        new=AsyncMock(return_value=field),
    ) as q:
        result = await applier._find_field("*\nPhone Number")

    assert result is field
    assert q.await_args.args[1] == "*\nPhone Number"


async def test_find_field_returns_none_when_all_fail():
    """_find_field returns None when no strategy finds the field."""
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value=None)
    applier.page.query_selector = AsyncMock(return_value=None)

    result = await applier._find_field("Unknown Label XYZ")
    assert result is None


# ── fill_form() status dict ────────────────────────────────────────────────────


async def test_fill_form_returns_status_dict():
    """fill_form returns a dict with a status per field."""
    applier = make_applier()
    field = MagicMock()
    field.evaluate = make_evaluate("input")
    field.get_attribute = AsyncMock(return_value="text")
    field.fill = AsyncMock()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))
    applier.page.locator = MagicMock(
        return_value=MagicMock(first=MagicMock(count=AsyncMock(return_value=0)))
    )

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"Name": "Alberto"}, cv_path="")

    assert isinstance(result, dict)
    assert result.get("Name") == "filled"


async def test_fill_form_skips_empty_answer():
    """fill_form marks fields with an empty answer as 'skipped'."""
    applier = make_applier()
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"Field": ""}, cv_path="")
    assert result.get("Field") == "skipped"


async def test_fill_form_skips_skip_sentinel():
    """fill_form marks fields with __SKIP__ as 'skipped'."""
    applier = make_applier()
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"Attach": "__SKIP__"}, cv_path="")
    assert result.get("Attach") == "skipped"


async def test_fill_form_marks_failed_when_field_not_found():
    """fill_form returns 'failed:not_found' when the field is not located."""
    applier = make_applier()
    # All strategies return None
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value=None)
    applier.page.query_selector = AsyncMock(return_value=None)
    applier.page.locator = MagicMock(
        return_value=MagicMock(first=MagicMock(count=AsyncMock(return_value=0)))
    )

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"Nonexistent Field": "value"}, cv_path="")

    assert result.get("Nonexistent Field") == "failed:not_found"


# ── _upload_cv() ──────────────────────────────────────────────────────────────


async def test_upload_cv_skips_when_no_path():
    """_upload_cv returns 'skipped' when cv_path is empty."""
    applier = make_applier()
    result = await applier._upload_cv("")
    assert result == "skipped"


async def test_upload_cv_falls_back_to_query_selector():
    """_upload_cv uses query_selector when locator.first.count returns 0."""
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
    """_upload_cv returns 'failed:no_file_input' when there is no file input."""
    applier = make_applier()
    empty_first = MagicMock()
    empty_first.count = AsyncMock(return_value=0)
    applier.page.locator = MagicMock(return_value=MagicMock(first=empty_first))
    applier.page.query_selector = AsyncMock(return_value=None)

    result = await applier._upload_cv("/path/cv.pdf")
    assert result == "failed:no_file_input"


# ── submit() new behaviors ────────────────────────────────────────────────────


async def test_submit_detects_form_still_visible_after_click():
    """submit() returns 'failed:validation_errors:...' when the form is still visible."""
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="some page without confirmation")
    applier.page.url = "https://boards.greenhouse.io/stripe/jobs/123"

    call_n = [0]

    async def qs_side(selector):
        call_n[0] += 1
        if "submit" in selector and call_n[0] == 1:
            return btn  # first call: finds the button
        return None

    applier.page.query_selector = qs_side

    # evaluate: (1) empty required fields, (2) form still visible, (3) error messages
    eval_calls = [[], True, []]
    eval_n = [0]

    async def eval_side(js, *args):
        result = eval_calls[eval_n[0]]
        eval_n[0] = min(eval_n[0] + 1, len(eval_calls) - 1)
        return result

    applier.page.evaluate = eval_side

    result = await applier.submit()
    assert result.startswith("failed:validation_errors")


async def test_submit_logs_empty_required_fields(caplog):
    """submit() logs a warning when required fields are empty before submitting."""

    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="thank you for applying")
    applier.page.query_selector = AsyncMock(return_value=btn)
    # evaluate: (1) empty required fields presentes, (2) form not visible after submit
    applier.page.evaluate = AsyncMock(side_effect=[["First Name *"], False, []])

    with caplog.at_level(logging.WARNING, logger="moonlighter.application.appliers.greenhouse"):
        await applier.submit()

    assert "First Name" in caplog.text


# ── logging ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_greenhouse_detect_logs_match(caplog):

    applier = make_applier("https://boards.greenhouse.io/stripe/jobs/1")
    with caplog.at_level(logging.DEBUG, logger="moonlighter.application.appliers.greenhouse"):
        await applier.detect()
    assert "detect: greenhouse" in caplog.text


@pytest.mark.asyncio
async def test_greenhouse_submit_logs_outcome(caplog):

    applier = make_applier("https://boards.greenhouse.io/stripe/jobs/1")
    submit_btn = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=submit_btn)
    applier.page.wait_for_load_state = AsyncMock()
    # simulates confirmation page
    applier.page.inner_text = AsyncMock(return_value="application submitted successfully")
    applier.page.url = "https://boards.greenhouse.io/confirmation"

    with caplog.at_level(logging.INFO, logger="moonlighter.application.appliers.greenhouse"):
        outcome = await applier.submit()

    assert "submit" in caplog.text
    assert outcome in ("submitted", "unverified")


# ── extract_fields: excludes upload-alternative fields ────────────────────────


async def test_extract_fields_excludes_upload_alternatives():
    """Attach/Anexar/Enter manually/Informe manualmente belong to the CV upload
    area (handled by _upload_cv) — they must not go to the LLM as text fields.

    "Anexar"/"Informe manualmente" are the real PT-BR labels _UPLOAD_LABELS
    matches on Brazilian Greenhouse forms; kept verbatim as functional data."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    labels = []
    for text in [
        "Attach",
        "Anexar",
        "Enter manually",
        "Informe manualmente",
        "First Name",
        "Phone",
    ]:
        m = MagicMock()
        m.inner_text = AsyncMock(return_value=text)
        labels.append(m)
    applier.page.query_selector_all = AsyncMock(return_value=labels)

    fields, _ = await applier.extract_fields()
    for excluded in ("Attach", "Anexar", "Enter manually", "Informe manualmente"):
        assert excluded not in fields
    assert "First Name" in fields
    assert "Phone" in fields


# ── fill_form: react-select (input role=combobox) ─────────────────────────────


async def test_fill_form_routes_combobox_input_to_custom_dropdown():
    """react-select: <input role=combobox> must go to the custom dropdown handler,
    not be treated as a text input (otherwise it types into the search and lies 'filled')."""
    applier = make_applier()
    field = MagicMock()
    field.evaluate = make_evaluate("input", combobox=True)  # tagName + combobox-check
    field.fill = AsyncMock()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))
    applier.page.locator = MagicMock(
        return_value=MagicMock(first=MagicMock(count=AsyncMock(return_value=0)))
    )
    applier._dropdown.select_custom_option = AsyncMock(return_value=True)  # dropdown handler

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form(
            {"Are you able to work from the office?": "Yes"}, cv_path=""
        )

    assert result["Are you able to work from the office?"] == "filled"
    applier._dropdown.select_custom_option.assert_awaited_once()  # routed to the dropdown handler
    field.fill.assert_not_called()  # did NOT treat it as a text input


async def test_fill_form_combobox_no_match_marks_failed_not_filled():
    """If the option is not found in the react-select, status is failed — never 'filled'."""
    applier = make_applier()
    field = MagicMock()
    # combobox, but single-value stays empty → nothing was selected → failed
    field.evaluate = make_evaluate("input", combobox=True, selected="")
    field.click = AsyncMock()
    field.type = AsyncMock()
    field.press = AsyncMock()
    field.fill = AsyncMock()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))
    applier.page.locator = MagicMock(
        return_value=MagicMock(first=MagicMock(count=AsyncMock(return_value=0)))
    )
    applier.page.evaluate = AsyncMock(return_value=False)  # no option matched
    applier.page.keyboard = MagicMock()
    applier.page.keyboard.press = AsyncMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"English level": "Fluent"}, cv_path="")

    assert result["English level"].startswith("failed")


# ── _find_field: for_id resolves but element is missing (159->163) ──────────


async def test_find_field_uses_the_lookup_when_for_points_nowhere():
    """A label whose `for` points at nothing still falls through to aria-label."""
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value="no-such-id")
    applier.page.query_selector = AsyncMock(return_value=None)
    field = MagicMock()

    with patch(
        "moonlighter.application.appliers.greenhouse.find_labeled_input",
        new=AsyncMock(return_value=field),
    ):
        assert await applier._find_field("Phone") is field


# ── fill_form: non-native element goes to the custom dropdown handler ──────


async def test_fill_form_routes_non_native_element_to_custom():
    applier = make_applier()
    field = MagicMock()

    async def ev(js, *a):
        if "combobox" in js or "aria-haspopup" in js or "select__input" in js:
            return False
        if "tagName" in js:
            return "div"  # non-native
        return None

    field.evaluate = ev
    applier._find_field = AsyncMock(return_value=field)
    applier._dropdown.fill_custom_element = AsyncMock(return_value=False)
    applier._upload_cv = AsyncMock(return_value="skipped")
    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({"Q": "A"}, cv_path="")
    assert status["Q"] == "failed:custom_element_unsupported"
