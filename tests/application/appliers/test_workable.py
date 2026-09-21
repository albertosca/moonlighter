import logging
from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.application.appliers.workable import WorkableApplier


def make_label_locator(field_mock=None):
    """Creates a mock Playwright Locator that returns field_mock via element_handle()."""
    locator = MagicMock()
    locator.count = AsyncMock(return_value=1 if field_mock else 0)
    locator.first = MagicMock()
    locator.first.element_handle = AsyncMock(return_value=field_mock)
    return locator


def make_applier(url="https://apply.workable.com/acme/j/ABCDEF1234/apply/"):
    page = MagicMock()
    page.url = url
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_load_state = AsyncMock()
    page.inner_text = AsyncMock(return_value="")
    page.get_by_label = MagicMock(return_value=make_label_locator(None))
    page.evaluate = AsyncMock(return_value=None)
    config = {}
    profile = {}
    return WorkableApplier(page, config, profile)


def make_evaluate(tag, combobox=False, selected=""):
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


async def test_detect_workable_url():
    applier = make_applier("https://apply.workable.com/acme/j/ABCDEF1234/apply/")
    assert await applier.detect() is True


async def test_detect_non_workable_url():
    applier = make_applier("https://boards.greenhouse.io/acme/jobs/1")
    assert await applier.detect() is False


async def test_workable_detect_logs_match(caplog):
    applier = make_applier("https://apply.workable.com/acme/j/ABCDEF1234/apply/")
    with caplog.at_level(logging.DEBUG, logger="moonlighter.application.appliers.workable"):
        await applier.detect()
    assert "detect: workable" in caplog.text


# ── extract_fields() ────────────────────────────────────────────────────────


async def test_extract_fields_returns_non_empty_labels():
    applier = make_applier()
    labels = []
    for text in ["First name", "", "Email"]:
        m = MagicMock()
        m.inner_text = AsyncMock(return_value=text)
        m.evaluate = AsyncMock(return_value=False)
        labels.append(m)
    applier.page.query_selector_all = AsyncMock(return_value=labels)

    fields, closed_set = await applier.extract_fields()
    assert fields == ["First name", "Email"]
    assert closed_set == frozenset()


async def test_extract_fields_reports_closed_set_labels():
    applier = make_applier()
    select_label = MagicMock()
    select_label.inner_text = AsyncMock(return_value="Are you authorized to work in the US?")
    select_label.evaluate = AsyncMock(return_value=True)
    text_label = MagicMock()
    text_label.inner_text = AsyncMock(return_value="First name")
    text_label.evaluate = AsyncMock(return_value=False)
    applier.page.query_selector_all = AsyncMock(return_value=[select_label, text_label])

    fields, closed_set = await applier.extract_fields()
    assert fields == ["Are you authorized to work in the US?", "First name"]
    assert closed_set == frozenset({"Are you authorized to work in the US?"})


async def test_extract_fields_excludes_resume_upload_label():
    applier = make_applier()
    label = MagicMock()
    label.inner_text = AsyncMock(return_value="Resume")
    label.evaluate = AsyncMock(return_value=False)
    applier.page.query_selector_all = AsyncMock(return_value=[label])

    fields, _ = await applier.extract_fields()
    assert "Resume" not in fields


async def test_extract_fields_falls_back_when_primary_selector_empty():
    applier = make_applier()
    fallback_label = MagicMock()
    fallback_label.inner_text = AsyncMock(return_value="Portfolio URL")
    fallback_label.evaluate = AsyncMock(return_value=False)

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


# ── fill_form() ──────────────────────────────────────────────────────────────


async def test_fill_form_fills_text_inputs():
    applier = make_applier()
    field = MagicMock()
    field.evaluate = make_evaluate("input")
    field.get_attribute = AsyncMock(return_value="text")
    field.fill = AsyncMock()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"First name": "Alberto"}, cv_path="")

    field.fill.assert_called_once_with("Alberto")


async def test_fill_form_skips_when_field_missing():
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value=None)
    applier.page.query_selector = AsyncMock(return_value=None)

    status = await applier.fill_form({"Nonexistent Field": "x"}, cv_path="")
    assert status["Nonexistent Field"] == "failed:not_found"


async def test_fill_form_skip_sentinel():
    applier = make_applier()
    status = await applier.fill_form({"Field1": "__SKIP__"}, cv_path="")
    assert status["Field1"] == "skipped"


async def test_fill_form_uploads_cv():
    applier = make_applier()
    file_locator_first = MagicMock()
    file_locator_first.count = AsyncMock(return_value=1)
    file_locator_first.set_input_files = AsyncMock()
    file_locator = MagicMock()
    file_locator.first = file_locator_first
    applier.page.locator = MagicMock(return_value=file_locator)

    status = await applier.fill_form({}, cv_path="/tmp/cv.pdf")
    assert status["__cv__"] == "filled"
    file_locator_first.set_input_files.assert_called_once_with("/tmp/cv.pdf")


async def test_fill_form_no_cv_path_skips_upload():
    applier = make_applier()
    status = await applier.fill_form({}, cv_path="")
    assert status["__cv__"] == "skipped"


# ── submit() ─────────────────────────────────────────────────────────────────


async def test_submit_returns_submitted_on_confirmation():
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="application submitted successfully")

    result = await applier.submit()
    assert result == "submitted"
    btn.click.assert_called_once()


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
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="thank you for applying")
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.evaluate = AsyncMock(side_effect=[["First name"], False, []])

    with caplog.at_level(logging.WARNING, logger="moonlighter.application.appliers.workable"):
        await applier.submit()
    assert "First name" in caplog.text


async def test_submit_detects_form_still_visible_after_click():
    """submit() returns 'failed:validation_errors:...' when the form is still visible."""
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="some page without confirmation")
    applier.page.url = "https://apply.workable.com/acme/j/ABCDEF1234/apply/"

    call_n = [0]

    async def qs_side(selector):
        call_n[0] += 1
        if "submit" in selector and call_n[0] == 1:
            return btn
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


# ── fill_form: custom dropdown / custom element routing ────────────────────────


async def test_fill_form_routes_combobox_to_custom_dropdown():
    applier = make_applier()
    field = MagicMock()
    field.evaluate = AsyncMock()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))
    applier._dropdown.is_custom_combobox = AsyncMock(return_value=True)
    applier._dropdown.select_custom_option = AsyncMock(return_value=True)

    status = await applier.fill_form({"English level": "Fluent"}, cv_path="")
    assert status["English level"] == "filled"
    applier._dropdown.select_custom_option.assert_awaited_once()


async def test_fill_form_combobox_no_match_marks_failed():
    applier = make_applier()
    field = MagicMock()
    field.evaluate = AsyncMock()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))
    applier._dropdown.is_custom_combobox = AsyncMock(return_value=True)
    applier._dropdown.select_custom_option = AsyncMock(return_value=False)

    status = await applier.fill_form({"English level": "Fluent"}, cv_path="")
    assert status["English level"] == "failed:custom_dropdown"


async def test_fill_form_routes_non_native_element_to_custom():
    applier = make_applier()
    field = MagicMock()
    field.evaluate = make_evaluate("div")
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))
    applier._dropdown.is_custom_combobox = AsyncMock(return_value=False)
    applier._dropdown.fill_custom_element = AsyncMock(return_value=True)

    status = await applier.fill_form({"Custom field": "value"}, cv_path="")
    assert status["Custom field"] == "filled"
    applier._dropdown.fill_custom_element.assert_awaited_once()


async def test_fill_form_non_native_element_unsupported():
    applier = make_applier()
    field = MagicMock()
    field.evaluate = make_evaluate("div")
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))
    applier._dropdown.is_custom_combobox = AsyncMock(return_value=False)
    applier._dropdown.fill_custom_element = AsyncMock(return_value=False)

    status = await applier.fill_form({"Custom field": "value"}, cv_path="")
    assert status["Custom field"] == "failed:custom_element_unsupported"


async def test_fill_form_exception_in_field_continues():
    applier = make_applier()
    field = MagicMock()
    field.evaluate = AsyncMock(side_effect=Exception("boom"))
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))
    applier._dropdown.is_custom_combobox = AsyncMock(return_value=False)

    status = await applier.fill_form({"Field": "value"}, cv_path="")
    assert status["Field"] == "failed:Exception"


# ── _find_field() ───────────────────────────────────────────────────────────


async def test_find_field_js_fallback_uses_for_attribute():
    """_find_field uses JS to normalize the label and look up by for-id when get_by_label fails."""
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value="phone_field")
    field = MagicMock()
    applier.page.query_selector = AsyncMock(return_value=field)

    result = await applier._find_field("Phone")
    assert result is field
    applier.page.query_selector.assert_called_once_with("#phone_field")


async def test_find_field_uses_the_lookup_when_for_points_nowhere():
    """A label whose `for` points at nothing still falls through to aria-label."""
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value="no-such-id")
    applier.page.query_selector = AsyncMock(return_value=None)
    field = MagicMock()

    with patch(
        "moonlighter.application.appliers.workable.find_labeled_input",
        new=AsyncMock(return_value=field),
    ):
        assert await applier._find_field("Phone") is field


# ── _upload_cv() ─────────────────────────────────────────────────────────────


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


async def test_upload_cv_exception_returns_failed():
    applier = make_applier()
    applier.page.locator = MagicMock(side_effect=Exception("boom"))

    result = await applier._upload_cv("/path/cv.pdf")
    assert result == "failed:Exception"


# ── radio groups ──────────────────────────────────────────────────────────────

_WK_GROUPS = [
    {
        "question": "Do you have at least 8 years of experience?",
        "options": ["YES", "NO"],
        "name": "QA_1",
    },
    {
        "question": "Expertise in large React applications with TypeScript",
        "options": ["YES", "NO"],
        "name": "QA_2",
    },
]


def make_radio_applier(dom=None):
    applier = make_applier()
    applier.page.evaluate = AsyncMock(return_value=dom if dom is not None else _WK_GROUPS)
    return applier


async def test_extract_fields_returns_each_screening_question_once():
    """Every screening question here is labelled YES/NO, so scanning <label>
    collapsed four distinct required questions into two dict keys and lost all
    four. Observed on a live Workable posting, 2026-08-04."""
    applier = make_radio_applier()

    def label(text):
        m = MagicMock()
        m.inner_text = AsyncMock(return_value=text)
        m.evaluate = AsyncMock(return_value=False)
        return m

    applier.page.query_selector_all = AsyncMock(
        return_value=[label("*\nFirst name"), label("YES"), label("NO")]
    )

    fields, _closed = await applier.extract_fields()

    assert "Do you have at least 8 years of experience?" in fields
    assert "Expertise in large React applications with TypeScript" in fields
    assert "YES" not in fields and "NO" not in fields
    assert "*\nFirst name" in fields
    assert len([f for f in fields if f.startswith("Do you have")]) == 1


async def test_fill_form_answers_a_screening_question_by_group_name():
    """YES appears under every question, so the group has to be addressed by its
    `name` — matching on the option label alone would hit the wrong question."""
    applier = make_radio_applier()

    with patch(
        "moonlighter.application.appliers.workable.select_radio_option",
        new=AsyncMock(return_value=True),
    ) as sel:
        status = await applier.fill_form(
            {"Expertise in large React applications with TypeScript": "Yes"}, cv_path=""
        )

    assert sel.await_args.args[1:] == ("QA_2", "YES")
    assert status["Expertise in large React applications with TypeScript"] == "filled"


async def test_fill_form_reports_an_unmatched_screening_answer():
    applier = make_radio_applier()

    status = await applier.fill_form(
        {"Do you have at least 8 years of experience?": "Maybe someday"}, cv_path=""
    )

    assert status["Do you have at least 8 years of experience?"] == "failed:no_matching_option"


async def test_fill_form_reports_a_screening_radio_that_cannot_be_clicked():
    """Same guarantee as everywhere else: a required question left unanswered
    never reads as success."""
    applier = make_radio_applier()

    with patch(
        "moonlighter.application.appliers.workable.select_radio_option",
        new=AsyncMock(return_value=False),
    ):
        status = await applier.fill_form(
            {"Do you have at least 8 years of experience?": "Yes"}, cv_path=""
        )

    assert (
        status["Do you have at least 8 years of experience?"] == "failed:radio_option_not_clickable"
    )


async def test_extract_fields_drops_the_upload_widget_label():
    """The upload widget's own label ("Choose file", and "Replace file" once a
    file is attached) is not a question. Left in, the LLM writes a useless answer
    for it and the fill loop reports failed:not_found for a CV that _upload_cv
    attached correctly — observed on a live posting."""
    applier = make_applier()
    applier.page.evaluate = AsyncMock(return_value=[])

    def label(text):
        m = MagicMock()
        m.inner_text = AsyncMock(return_value=text)
        m.evaluate = AsyncMock(return_value=False)
        return m

    applier.page.query_selector_all = AsyncMock(
        return_value=[label("Choose file"), label("Replace file"), label("Headline (Optional)")]
    )

    fields, _closed = await applier.extract_fields()

    assert "Choose file" not in fields
    assert "Replace file" not in fields
    assert "Headline (Optional)" in fields


async def test_fill_form_skips_a_file_input_reached_by_label():
    """Belt and braces: if an upload label does slip through, the loop must not
    try to type into the file input — that is _upload_cv's field."""
    applier = make_applier()
    applier.page.evaluate = AsyncMock(return_value=[])
    field = MagicMock()

    async def ev(js, *a):
        if "tagName" in js:
            return "input"
        return False  # not a custom combobox, not a closed set

    field.evaluate = ev
    field.get_attribute = AsyncMock(return_value="file")
    field.fill = AsyncMock()

    with patch(
        "moonlighter.application.appliers.workable.find_labeled_input",
        new=AsyncMock(return_value=field),
    ):
        applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
        status = await applier.fill_form({"Attach something": "text"}, cv_path="")

    field.fill.assert_not_called()
    assert status["Attach something"] == "skipped"
