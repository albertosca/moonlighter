import logging
from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.application.appliers.linkedin import LinkedInApplier
from playwright.async_api import TimeoutError as PlaywrightTimeout


def make_applier(url="https://www.linkedin.com/jobs/view/123"):
    page = MagicMock()
    page.url = url
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.inner_text = AsyncMock(return_value="")  # no confirmation by default
    return LinkedInApplier(page, {}, {})


# ── detect() ─────────────────────────────────────────────────────────────────


async def test_detect_linkedin_jobs_url():
    applier = make_applier("https://www.linkedin.com/jobs/view/123")
    assert await applier.detect() is True


async def test_detect_linkedin_non_jobs_url():
    applier = make_applier("https://www.linkedin.com/in/profile")
    assert await applier.detect() is False


async def test_detect_non_linkedin():
    applier = make_applier("https://greenhouse.io/x")
    assert await applier.detect() is False


# ── is_easy_apply() ──────────────────────────────────────────────────────────


async def test_is_easy_apply_true():
    applier = make_applier()
    btn = MagicMock()
    btn.inner_text = AsyncMock(return_value="Easy Apply")
    applier.page.query_selector = AsyncMock(return_value=btn)
    assert await applier.is_easy_apply() is True


async def test_is_easy_apply_false():
    applier = make_applier()
    btn = MagicMock()
    btn.inner_text = AsyncMock(return_value="Apply")
    applier.page.query_selector = AsyncMock(return_value=btn)
    assert await applier.is_easy_apply() is False


async def test_is_easy_apply_no_button():
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    assert await applier.is_easy_apply() is False


async def test_is_easy_apply_case_insensitive():
    applier = make_applier()
    btn = MagicMock()
    btn.inner_text = AsyncMock(return_value="EASY APPLY")
    applier.page.query_selector = AsyncMock(return_value=btn)
    assert await applier.is_easy_apply() is True


# ── extract_fields() ──────────────────────────────────────────────────────────


async def test_extract_fields_clicks_apply_button():
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_selector = AsyncMock()
    applier.page.query_selector_all = AsyncMock(return_value=[])

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.extract_fields()

    btn.click.assert_called_once()


async def test_extract_fields_waits_for_modal():
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_selector = AsyncMock()
    applier.page.query_selector_all = AsyncMock(return_value=[])

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.extract_fields()

    applier.page.wait_for_selector.assert_called_once_with(".jobs-easy-apply-modal", timeout=10000)


async def test_extract_fields_returns_labels_from_modal():
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_selector = AsyncMock()

    label = MagicMock()
    label.inner_text = AsyncMock(return_value="Phone Number")
    applier.page.query_selector_all = AsyncMock(return_value=[label])

    with patch("asyncio.sleep", new=AsyncMock()):
        fields, _ = await applier.extract_fields()

    assert "Phone Number" in fields


async def test_extract_fields_timeout_on_modal():
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeout("timeout"))

    with patch("asyncio.sleep", new=AsyncMock()):
        fields, _ = await applier.extract_fields()

    assert fields == []


async def test_extract_fields_no_apply_button_returns_empty():
    """When no apply button, btn.click is skipped; empty fields returned (no modal)."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    applier.page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeout("timeout"))

    with patch("asyncio.sleep", new=AsyncMock()):
        fields, _ = await applier.extract_fields()

    assert fields == []


# ── fill_form() ───────────────────────────────────────────────────────────────


async def test_fill_form_uses_modal_selector():
    """Query selector uses .jobs-easy-apply-modal prefix for labels."""
    applier = make_applier()
    selectors_used = []

    async def qs(selector):
        selectors_used.append(selector)
        return

    applier.page.query_selector = qs

    status = await applier.fill_form({"Phone": "555-1234"}, cv_path="")
    assert any(".jobs-easy-apply-modal" in s for s in selectors_used)
    assert status["Phone"] == "failed:not_found"


async def test_fill_form_fills_input_fields():
    applier = make_applier()
    label = MagicMock()
    label.get_attribute = AsyncMock(return_value="phone")
    field = MagicMock()
    field.evaluate = AsyncMock(return_value="input")
    field.get_attribute = AsyncMock(return_value="text")
    field.fill = AsyncMock()

    async def qs(selector):
        if "label" in selector:
            return label
        return field

    applier.page.query_selector = qs

    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({"Phone": "555-1234"}, cv_path="")

    field.fill.assert_called_once_with("555-1234")
    assert status["Phone"] == "filled"


async def test_fill_form_fills_textarea_fields():
    applier = make_applier()
    label = MagicMock()
    label.get_attribute = AsyncMock(return_value="summary")
    field = MagicMock()
    field.evaluate = AsyncMock(return_value="textarea")
    field.fill = AsyncMock()

    async def qs(selector):
        if "label" in selector:
            return label
        return field

    applier.page.query_selector = qs

    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({"Summary": "Experienced engineer"}, cv_path="")

    field.fill.assert_called_once_with("Experienced engineer")
    assert status["Summary"] == "filled"


async def test_fill_form_skips_sentinel_answers():
    """A sentinel answer (e.g. __NEEDS_REVIEW__) must never be typed into the form.

    field.evaluate/get_attribute are configured (mirroring test_fill_form_fills_input_fields)
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
        status = await applier.fill_form({"Q1": "__NEEDS_REVIEW__"}, cv_path="")
    field.fill.assert_not_called()
    assert status["Q1"] == "skipped"


async def test_fill_form_uploads_cv_via_modal_selector():
    """CV upload uses .jobs-easy-apply-modal input[type='file'] selector."""
    applier = make_applier()
    file_input = MagicMock()
    file_input.set_input_files = AsyncMock()

    selectors_used = []

    async def qs(selector):
        selectors_used.append(selector)
        if "file" in selector:
            return file_input
        return None

    applier.page.query_selector = qs

    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({}, cv_path="/cv.pdf")

    file_input.set_input_files.assert_called_once_with("/cv.pdf")
    assert any(".jobs-easy-apply-modal" in s and "file" in s for s in selectors_used)
    assert status["__cv__"] == "filled"


async def test_fill_form_exception_continues_to_next_field(caplog):
    """Exception on one field doesn't prevent subsequent fields from being filled."""
    applier = make_applier()
    filled = []

    async def qs(selector):
        if "Field1" in selector:
            raise Exception("fail")
        if "Field2" in selector:
            label = MagicMock()
            label.get_attribute = AsyncMock(return_value="f2")
            return label
        if selector == "#f2":
            field = MagicMock()
            field.evaluate = AsyncMock(return_value="input")
            field.get_attribute = AsyncMock(return_value="text")

            async def do_fill(val):
                filled.append(val)

            field.fill = do_fill
            return field
        return None

    applier.page.query_selector = qs

    with (
        patch("asyncio.sleep", new=AsyncMock()),
        caplog.at_level(logging.DEBUG, logger="moonlighter.application.appliers.linkedin"),
    ):
        status = await applier.fill_form({"Field1": "v1", "Field2": "v2"}, cv_path="")

    assert "v2" in filled
    assert "fill failed for 'Field1'" in caplog.text
    assert status["Field1"] == "failed:Exception"
    assert status["Field2"] == "filled"


# ── submit() — multi-step ─────────────────────────────────────────────────────


async def test_submit_clicks_submit_button_directly():
    """Submit button present immediately + confirmation → True."""
    applier = make_applier()
    submit_btn = MagicMock()
    submit_btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=submit_btn)
    applier.page.inner_text = AsyncMock(return_value="Your application was sent")

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.submit()

    assert result == "submitted"
    submit_btn.click.assert_called_once()


async def test_submit_unverified_without_confirmation():
    """RELIABILITY-01: clicou Submit mas sem 'application sent' → 'unverified'."""
    applier = make_applier()
    submit_btn = MagicMock()
    submit_btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=submit_btn)
    applier.page.inner_text = AsyncMock(return_value="Phone Number Years of Experience")
    applier.page.evaluate = AsyncMock(return_value=False)  # modal is no longer visible

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.submit()

    assert result == "unverified"


async def test_submit_clicks_next_then_submit():
    """Next button clicked once, then Submit button → True."""
    applier = make_applier()
    submit_btn = MagicMock()
    submit_btn.click = AsyncMock()
    next_btn = MagicMock()
    next_btn.click = AsyncMock()

    call_count = [0]

    async def qs(selector):
        call_count[0] += 1
        # First call: no submit button (returns None)
        # Second call (next btn): returns next_btn
        # Third call: returns submit_btn
        # Fourth call (next btn again): won't be reached
        if call_count[0] == 1:
            return None  # no submit btn first iteration
        if call_count[0] == 2:
            return next_btn  # next btn
        if call_count[0] == 3:
            return submit_btn  # submit btn found
        return None

    applier.page.query_selector = qs
    applier.page.inner_text = AsyncMock(return_value="Your application was sent")

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.submit()

    assert result == "submitted"
    next_btn.click.assert_called_once()
    submit_btn.click.assert_called_once()


async def test_submit_no_buttons_returns_failed():
    """No submit or next buttons → 'failed'."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.submit()

    assert result == "failed"


async def test_submit_max_10_steps():
    """Loop stops after 10 iterations even if next_btn always present."""
    applier = make_applier()
    next_btn = MagicMock()
    next_btn.click = AsyncMock()

    next_calls = [0]

    async def qs(selector):
        # Never return submit button (selector contains 'Submit application')
        if "Submit application" in selector:
            return None
        # Always return next button (selector contains 'Continue to next step')
        next_calls[0] += 1
        return next_btn

    applier.page.query_selector = qs

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.submit()

    assert result == "failed"
    assert next_btn.click.call_count == 10


async def test_submit_exception_returns_failed():
    """Exception during click → breaks loop → 'failed'."""
    applier = make_applier()
    submit_btn = MagicMock()
    submit_btn.click = AsyncMock(side_effect=Exception("click failed"))
    applier.page.query_selector = AsyncMock(return_value=submit_btn)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.submit()

    assert result == "failed"


async def test_extract_fields_falls_back_when_primary_modal_selector_empty():
    """Empty primary modal selector → alternative selector tried."""
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_selector = AsyncMock()

    fallback_label = MagicMock()
    fallback_label.inner_text = AsyncMock(return_value="Phone Number")

    call_count = [0]

    async def qs_all(selector):
        call_count[0] += 1
        if call_count[0] == 1:
            return []
        return [fallback_label]

    applier.page.query_selector_all = qs_all

    with patch("asyncio.sleep", new=AsyncMock()):
        fields, _ = await applier.extract_fields()

    assert "Phone Number" in fields
    assert call_count[0] >= 2


async def test_extract_fields_reports_closed_set_labels():
    applier = make_applier()
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


# ── branches de borda (cobertura) ──────────────────────────────────────────


async def test_extract_fields_apply_click_exception_returns_empty():
    """Click on the Apply button raises → extract_fields returns [] (26-27)."""
    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock(side_effect=Exception("detached"))
    applier.page.query_selector = AsyncMock(return_value=btn)
    with patch("asyncio.sleep", new=AsyncMock()):
        assert await applier.extract_fields() == ([], frozenset())


async def test_extract_fields_skips_empty_modal_label():
    """Label with empty text in the modal is ignored (44->42)."""
    applier = make_applier()
    empty = MagicMock()
    empty.inner_text = AsyncMock(return_value="   ")
    real = MagicMock()
    real.inner_text = AsyncMock(return_value="Phone")
    applier.page.query_selector = AsyncMock(return_value=None)  # no Apply button
    applier.page.query_selector_all = AsyncMock(return_value=[empty, real])
    with patch("asyncio.sleep", new=AsyncMock()):
        result, _ = await applier.extract_fields()
    assert result == ["Phone"]


async def test_fill_form_skips_label_without_for():
    """Label with no for attribute → field not filled (59->51)."""
    applier = make_applier()
    label = MagicMock()
    label.get_attribute = AsyncMock(return_value=None)
    applier.page.query_selector = AsyncMock(return_value=label)
    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({"Q": "A"}, cv_path="")
    assert status["Q"] == "failed:not_found"


async def test_fill_form_skips_when_field_missing():
    """for=fid but #fid doesn't exist → field not filled (61->51)."""
    applier = make_applier()
    label = MagicMock()
    label.get_attribute = AsyncMock(return_value="fid")

    async def qs(selector):
        return label if "label" in selector else None

    applier.page.query_selector = qs
    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({"Q": "A"}, cv_path="")
    assert status["Q"] == "failed:not_found"


async def test_fill_form_cv_upload_not_found():
    """No file input found in the modal → status surfaces failed:not_found, not silently dropped."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    with patch("asyncio.sleep", new=AsyncMock()):
        status = await applier.fill_form({}, cv_path="/cv.pdf")
    assert status["__cv__"] == "failed:not_found"


async def test_fill_form_swallows_cv_upload_exception(caplog):
    """Exception while uploading the CV is swallowed (74-75)."""
    applier = make_applier()
    file_input = MagicMock()
    file_input.set_input_files = AsyncMock(side_effect=Exception("io"))

    async def qs(selector):
        return file_input if "file" in selector else None

    applier.page.query_selector = qs
    with (
        patch("asyncio.sleep", new=AsyncMock()),
        caplog.at_level(logging.DEBUG, logger="moonlighter.application.appliers.linkedin"),
    ):
        status = await applier.fill_form({}, cv_path="/cv.pdf")
    assert "CV upload failed" in caplog.text
    assert status["__cv__"] == "failed:Exception"
