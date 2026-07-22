import logging
from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.application.appliers.smartrecruiters import SmartRecruitersApplier


def mock_element(tag="spl-input", label=None, text=None, native=None):
    """A mock Playwright ElementHandle for one of the spl-* custom elements."""
    el = MagicMock()
    el.evaluate = AsyncMock(return_value=tag)
    el.get_attribute = AsyncMock(return_value=label)
    el.inner_text = AsyncMock(return_value=text or "")
    el.click = AsyncMock()
    el.query_selector = AsyncMock(return_value=native)
    return el


def make_applier(url="https://jobs.smartrecruiters.com/oneclick-ui/company/Acme/publication/abc"):
    page = MagicMock()
    page.url = url
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_load_state = AsyncMock()
    page.inner_text = AsyncMock(return_value="")
    page.evaluate = AsyncMock(return_value=None)
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    config = {}
    profile = {}
    return SmartRecruitersApplier(page, config, profile)


# ── detect() ─────────────────────────────────────────────────────────────────


async def test_detect_smartrecruiters_url():
    applier = make_applier(
        "https://jobs.smartrecruiters.com/oneclick-ui/company/Acme/publication/abc"
    )
    assert await applier.detect() is True


async def test_detect_rejects_listing_page_without_oneclick_ui():
    applier = make_applier("https://jobs.smartrecruiters.com/Acme/744-software-engineer")
    assert await applier.detect() is False


async def test_detect_rejects_other_ats():
    applier = make_applier("https://boards.greenhouse.io/acme/jobs/1")
    assert await applier.detect() is False


async def test_smartrecruiters_detect_logs_match(caplog):
    applier = make_applier()
    with caplog.at_level(logging.DEBUG, logger="moonlighter.application.appliers.smartrecruiters"):
        await applier.detect()
    assert "detect: smartrecruiters" in caplog.text


# ── extract_fields() ────────────────────────────────────────────────────────


async def test_extract_fields_returns_labels_and_closed_set():
    applier = make_applier()
    els = [
        mock_element(tag="spl-input", label="First name"),
        mock_element(tag="spl-select", label="Country"),
        mock_element(tag="spl-dropdown", label="Notice period"),
        mock_element(tag="spl-input", label=None),  # no label attr -> skipped
    ]
    applier.page.query_selector_all = AsyncMock(return_value=els)

    labels, closed_set = await applier.extract_fields()
    assert labels == ["First name", "Country", "Notice period"]
    assert closed_set == frozenset({"Country", "Notice period"})


async def test_extract_fields_empty_when_no_matches():
    applier = make_applier()
    applier.page.query_selector_all = AsyncMock(return_value=[])
    labels, closed_set = await applier.extract_fields()
    assert labels == []
    assert closed_set == frozenset()


# ── _find_field() ────────────────────────────────────────────────────────────


async def test_find_field_queries_expected_selector():
    applier = make_applier()
    el = mock_element(tag="spl-input", label="First name")
    applier.page.query_selector = AsyncMock(return_value=el)

    found = await applier._find_field("First name")
    assert found is el
    call_selector = applier.page.query_selector.call_args[0][0]
    assert 'spl-input[label="First name"]' in call_selector
    assert 'spl-phone-field[label="First name"]' in call_selector


# ── _fill_one() dispatch ─────────────────────────────────────────────────────


async def test_fill_one_skips_sentinel_answer():
    applier = make_applier()
    assert await applier._fill_one("Field", "__SKIP__") == "skipped"


async def test_fill_one_not_found():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    assert await applier._fill_one("Missing", "value") == "failed:not_found"


async def test_fill_one_plain_input_fills_native_control():
    applier = make_applier()
    native = MagicMock()
    native.fill = AsyncMock()
    el = mock_element(tag="spl-input", label="First name", native=native)
    applier.page.query_selector = AsyncMock(return_value=el)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._fill_one("First name", "Alberto")
    assert result == "filled"
    native.fill.assert_called_once_with("Alberto")


async def test_fill_one_no_native_control():
    applier = make_applier()
    el = mock_element(tag="spl-input", label="First name", native=None)
    applier.page.query_selector = AsyncMock(return_value=el)
    assert await applier._fill_one("First name", "Alberto") == "failed:no_native_control"


async def test_fill_one_routes_closed_set_to_dropdown_handler():
    applier = make_applier()
    el = mock_element(tag="spl-select", label="Country")
    applier.page.query_selector = AsyncMock(return_value=el)
    with patch.object(
        applier, "_fill_closed_set", new=AsyncMock(return_value="filled")
    ) as mock_fill:
        result = await applier._fill_one("Country", "Brazil")
    assert result == "filled"
    mock_fill.assert_called_once_with(el, "Country", "Brazil")


async def test_fill_one_routes_autocomplete_to_handler():
    applier = make_applier()
    el = mock_element(tag="spl-autocomplete", label="City")
    applier.page.query_selector = AsyncMock(return_value=el)
    with patch.object(
        applier, "_fill_autocomplete", new=AsyncMock(return_value="filled")
    ) as mock_fill:
        result = await applier._fill_one("City", "Sao Paulo")
    assert result == "filled"
    mock_fill.assert_called_once_with(el, "City", "Sao Paulo")


async def test_fill_one_exception_returns_failed():
    applier = make_applier()
    el = mock_element(tag="spl-input", label="First name")
    el.evaluate = AsyncMock(side_effect=Exception("boom"))
    applier.page.query_selector = AsyncMock(return_value=el)
    result = await applier._fill_one("First name", "Alberto")
    assert result.startswith("failed:")


# ── _fill_closed_set() ───────────────────────────────────────────────────────


async def test_fill_closed_set_clicks_matching_option():
    applier = make_applier()
    field = mock_element(tag="spl-select", label="Country")
    option_yes = MagicMock()
    option_yes.inner_text = AsyncMock(return_value="Brazil")
    option_yes.click = AsyncMock()
    option_no = MagicMock()
    option_no.inner_text = AsyncMock(return_value="Argentina")
    option_no.click = AsyncMock()
    applier.page.query_selector_all = AsyncMock(return_value=[option_no, option_yes])

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._fill_closed_set(field, "Country", "Brazil")
    assert result == "filled"
    option_yes.click.assert_called_once()
    option_no.click.assert_not_called()


async def test_fill_closed_set_no_match_presses_escape():
    applier = make_applier()
    field = mock_element(tag="spl-select", label="Country")
    option = MagicMock()
    option.inner_text = AsyncMock(return_value="Argentina")
    applier.page.query_selector_all = AsyncMock(return_value=[option])

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._fill_closed_set(field, "Country", "Brazil")
    assert result == "failed:custom_dropdown"
    applier.page.keyboard.press.assert_called_once_with("Escape")


async def test_fill_closed_set_skips_blank_option_text():
    """Some spl-select-option elements render with no text yet (e.g. a
    loading placeholder) — those must be filtered out of the candidate pool
    rather than passed to match_option_locally as an empty string."""
    applier = make_applier()
    field = mock_element(tag="spl-select", label="Country")
    blank = MagicMock()
    blank.inner_text = AsyncMock(return_value="   ")
    blank.click = AsyncMock()
    option_yes = MagicMock()
    option_yes.inner_text = AsyncMock(return_value="Brazil")
    option_yes.click = AsyncMock()
    applier.page.query_selector_all = AsyncMock(return_value=[blank, option_yes])

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._fill_closed_set(field, "Country", "Brazil")
    assert result == "filled"
    option_yes.click.assert_called_once()
    blank.click.assert_not_called()


async def test_fill_closed_set_no_options_found():
    applier = make_applier()
    field = mock_element(tag="spl-select", label="Country")
    applier.page.query_selector_all = AsyncMock(return_value=[])
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._fill_closed_set(field, "Country", "Brazil")
    assert result == "failed:custom_dropdown"


async def test_fill_closed_set_exception_returns_failed():
    applier = make_applier()
    field = mock_element(tag="spl-select", label="Country")
    field.click = AsyncMock(side_effect=Exception("boom"))
    result = await applier._fill_closed_set(field, "Country", "Brazil")
    assert result.startswith("failed:")


# ── _fill_autocomplete() ─────────────────────────────────────────────────────


async def test_fill_autocomplete_clicks_suggestion():
    applier = make_applier()
    native = MagicMock()
    native.click = AsyncMock()
    native.type = AsyncMock()
    field = mock_element(tag="spl-autocomplete", label="City", native=native)
    suggestion = MagicMock()
    suggestion.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=suggestion)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._fill_autocomplete(field, "City", "Sao Paulo")
    assert result == "filled"
    native.type.assert_called_once_with("Sao Paulo", delay=30)
    suggestion.click.assert_called_once()


async def test_fill_autocomplete_no_suggestion_still_reports_filled():
    applier = make_applier()
    native = MagicMock()
    native.click = AsyncMock()
    native.type = AsyncMock()
    field = mock_element(tag="spl-autocomplete", label="City", native=native)
    applier.page.query_selector = AsyncMock(return_value=None)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._fill_autocomplete(field, "City", "Sao Paulo")
    assert result == "filled"


async def test_fill_autocomplete_no_native_control():
    applier = make_applier()
    field = mock_element(tag="spl-autocomplete", label="City", native=None)
    result = await applier._fill_autocomplete(field, "City", "Sao Paulo")
    assert result == "failed:no_native_control"


async def test_fill_autocomplete_exception_returns_failed():
    applier = make_applier()
    native = MagicMock()
    native.click = AsyncMock(side_effect=Exception("boom"))
    field = mock_element(tag="spl-autocomplete", label="City", native=native)
    result = await applier._fill_autocomplete(field, "City", "Sao Paulo")
    assert result.startswith("failed:")


# ── _upload_cv() ──────────────────────────────────────────────────────────────


async def test_upload_cv_no_path_skips():
    applier = make_applier()
    assert await applier._upload_cv("") == "skipped"


async def test_upload_cv_via_dropzone_scoped_input():
    applier = make_applier()
    file_input = MagicMock()
    file_input.set_input_files = AsyncMock()
    dropzone = MagicMock()
    dropzone.query_selector = AsyncMock(return_value=file_input)
    applier.page.query_selector = AsyncMock(return_value=dropzone)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._upload_cv("/tmp/cv.pdf")
    assert result == "filled"
    file_input.set_input_files.assert_called_once_with("/tmp/cv.pdf")


async def test_upload_cv_falls_back_to_page_level_file_input():
    applier = make_applier()
    dropzone = MagicMock()
    dropzone.query_selector = AsyncMock(return_value=None)
    file_input = MagicMock()
    file_input.set_input_files = AsyncMock()

    async def qs(selector):
        if selector == "spl-dropzone":
            return dropzone
        if selector == "input[type='file']":
            return file_input
        return None

    applier.page.query_selector = qs
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._upload_cv("/tmp/cv.pdf")
    assert result == "filled"
    file_input.set_input_files.assert_called_once_with("/tmp/cv.pdf")


async def test_upload_cv_no_file_input_found():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    result = await applier._upload_cv("/tmp/cv.pdf")
    assert result == "failed:no_file_input"


async def test_upload_cv_exception_returns_failed():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(side_effect=Exception("boom"))
    result = await applier._upload_cv("/tmp/cv.pdf")
    assert result.startswith("failed:")


# ── _is_final_step() / _click_next() ─────────────────────────────────────────


async def test_is_final_step_true_when_no_button():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    assert await applier._is_final_step() is True


async def test_is_final_step_false_for_next_button():
    applier = make_applier()
    btn = MagicMock()
    btn.inner_text = AsyncMock(return_value="Next")
    applier.page.query_selector = AsyncMock(return_value=btn)
    assert await applier._is_final_step() is False


async def test_is_final_step_true_for_submit_button():
    applier = make_applier()
    btn = MagicMock()
    btn.inner_text = AsyncMock(return_value="Submit application")
    applier.page.query_selector = AsyncMock(return_value=btn)
    assert await applier._is_final_step() is True


async def test_click_next_success():
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    assert await applier._click_next() is True
    btn.click.assert_called_once()


async def test_click_next_no_button():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    assert await applier._click_next() is False


async def test_click_next_exception_returns_false():
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock(side_effect=Exception("boom"))
    applier.page.query_selector = AsyncMock(return_value=btn)
    assert await applier._click_next() is False


# ── fill_form() orchestration ─────────────────────────────────────────────────


async def test_fill_form_single_step_happy_path():
    applier = make_applier()
    with (
        patch.object(
            applier, "extract_fields", new=AsyncMock(return_value=(["First name"], frozenset()))
        ),
        patch.object(applier, "_fill_one", new=AsyncMock(return_value="filled")) as mock_fill_one,
        patch.object(applier, "_is_final_step", new=AsyncMock(return_value=True)),
        patch.object(applier, "_click_next", new=AsyncMock(return_value=True)) as mock_next,
    ):
        applier.page.query_selector = AsyncMock(return_value=None)  # no spl-dropzone
        status = await applier.fill_form({"First name": "Alberto"}, cv_path="")
    assert status["First name"] == "filled"
    assert status["__cv__"] == "skipped"
    mock_fill_one.assert_called_once_with("First name", "Alberto")
    mock_next.assert_not_called()


async def test_fill_form_walks_multiple_steps():
    applier = make_applier()
    extract_calls = [
        (["First name"], frozenset()),
        (["Notice period"], frozenset({"Notice period"})),
    ]
    with (
        patch.object(applier, "extract_fields", new=AsyncMock(side_effect=extract_calls)),
        patch.object(applier, "_fill_one", new=AsyncMock(return_value="filled")) as mock_fill_one,
        patch.object(applier, "_is_final_step", new=AsyncMock(side_effect=[False, True])),
        patch.object(applier, "_click_next", new=AsyncMock(return_value=True)) as mock_next,
    ):
        applier.page.query_selector = AsyncMock(return_value=None)
        status = await applier.fill_form(
            {"First name": "Alberto", "Notice period": "2 weeks"}, cv_path=""
        )
    assert status["First name"] == "filled"
    assert status["Notice period"] == "filled"
    assert mock_fill_one.call_count == 2
    mock_next.assert_called_once()


async def test_fill_form_uploads_cv_when_dropzone_seen():
    applier = make_applier()
    with (
        patch.object(applier, "extract_fields", new=AsyncMock(return_value=([], frozenset()))),
        patch.object(applier, "_is_final_step", new=AsyncMock(return_value=True)),
        patch.object(applier, "_upload_cv", new=AsyncMock(return_value="filled")) as mock_upload,
    ):
        applier.page.query_selector = AsyncMock(return_value=MagicMock())  # spl-dropzone found
        status = await applier.fill_form({}, cv_path="/tmp/cv.pdf")
    assert status["__cv__"] == "filled"
    mock_upload.assert_called_once_with("/tmp/cv.pdf")


async def test_fill_form_wizard_too_long_reports_failure():
    applier = make_applier()
    with (
        patch.object(applier, "extract_fields", new=AsyncMock(return_value=([], frozenset()))),
        patch.object(applier, "_is_final_step", new=AsyncMock(return_value=False)),
        patch.object(applier, "_click_next", new=AsyncMock(return_value=True)),
    ):
        applier.page.query_selector = AsyncMock(return_value=None)
        status = await applier.fill_form({}, cv_path="")
    assert status["__wizard__"] == "failed:wizard_too_long"


async def test_fill_form_skips_step_label_not_in_answers():
    """A step can surface a field the caller never asked about (e.g. a
    read-only or already-prefilled control) — fill_form must skip it rather
    than blow up, and still process the labels it does have an answer for."""
    applier = make_applier()
    with (
        patch.object(
            applier,
            "extract_fields",
            new=AsyncMock(return_value=(["First name", "Unasked field"], frozenset())),
        ),
        patch.object(applier, "_fill_one", new=AsyncMock(return_value="filled")) as mock_fill_one,
        patch.object(applier, "_is_final_step", new=AsyncMock(return_value=True)),
        patch.object(applier, "_click_next", new=AsyncMock(return_value=True)),
    ):
        applier.page.query_selector = AsyncMock(return_value=None)
        status = await applier.fill_form({"First name": "Alberto"}, cv_path="")
    assert status["First name"] == "filled"
    assert "Unasked field" not in status
    mock_fill_one.assert_called_once_with("First name", "Alberto")


async def test_fill_form_navigation_failure_stops_and_reports():
    applier = make_applier()
    with (
        patch.object(applier, "extract_fields", new=AsyncMock(return_value=([], frozenset()))),
        patch.object(applier, "_is_final_step", new=AsyncMock(return_value=False)),
        patch.object(applier, "_click_next", new=AsyncMock(return_value=False)) as mock_next,
    ):
        applier.page.query_selector = AsyncMock(return_value=None)
        status = await applier.fill_form({}, cv_path="")
    assert status["__wizard__"] == "failed:navigation_at_step_1"
    mock_next.assert_called_once()


# ── submit() ───────────────────────────────────────────────────────────────────


async def test_submit_returns_submitted_on_confirmation():
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.inner_text = AsyncMock(return_value="thank you for applying")

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
    btn.click = AsyncMock(side_effect=Exception("boom"))
    applier.page.query_selector = AsyncMock(return_value=btn)
    result = await applier.submit()
    assert result == "failed"


async def test_submit_validation_errors_still_visible():
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.inner_text = AsyncMock(return_value="")
    applier.page.evaluate = AsyncMock(side_effect=[True, ["First name is required"]])

    result = await applier.submit()
    assert result.startswith("failed:validation_errors")
