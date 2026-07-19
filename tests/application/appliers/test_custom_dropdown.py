import logging
from unittest.mock import AsyncMock, MagicMock, patch

from gauntler.application.appliers.custom_dropdown import CustomDropdownFiller

LOGGER_NAME = "gauntler.application.appliers.custom_dropdown"


def make_filler():
    page = MagicMock()
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.evaluate = AsyncMock(return_value=None)
    config = {}
    profile = {}
    return CustomDropdownFiller(page, config, profile)


# ── select_custom_option() ──────────────────────────────────────────────────


async def test_select_custom_option_clicks_and_selects():
    """select_custom_option: local match on a static option, clicks the exact one and VERIFIES."""
    filler = make_filler()
    element = MagicMock()
    element.click = AsyncMock()
    element.type = AsyncMock()
    element.press = AsyncMock()
    element.scroll_into_view_if_needed = AsyncMock()
    filler._visible_options = AsyncMock(return_value=["Yes", "No"])
    filler._click_option_exact = AsyncMock(return_value=True)
    filler._selected_value = AsyncMock(return_value="Yes")
    filler.page.keyboard = MagicMock()
    filler.page.keyboard.press = AsyncMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await filler.select_custom_option(element, "Status", "Yes")

    assert result is True
    filler._click_option_exact.assert_awaited_with("Yes", element, [])  # clicked the exact option
    filler.page.keyboard.press.assert_not_called()


async def test_select_custom_option_uses_llm_for_descriptive_options():
    """When the local match fails (phrase-style options) the LLM chooses among the REAL
    options, WITHOUT typing (regression: typing 'Fluent' would filter to 'not able to speak
    fluently' and a blind Enter would grab the negative one)."""
    filler = make_filler()
    element = MagicMock()
    element.click = AsyncMock()
    element.type = AsyncMock()
    element.press = AsyncMock()
    element.scroll_into_view_if_needed = AsyncMock()
    cefr = [
        "I can read simple texts",
        "I can understand e-mails but I'm not able to speak fluently",
        "Native or bilingual proficiency",
    ]
    filler._visible_options = AsyncMock(return_value=cefr)
    filler._click_option_exact = AsyncMock(return_value=True)
    filler._selected_value = AsyncMock(return_value="Native or bilingual proficiency")
    filler._llm_pick = AsyncMock(return_value="Native or bilingual proficiency")
    filler.page.keyboard = MagicMock()
    filler.page.keyboard.press = AsyncMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await filler.select_custom_option(element, "English level", "Fluent")

    assert result is True
    filler._llm_pick.assert_awaited_once()
    filler._click_option_exact.assert_awaited_with("Native or bilingual proficiency", element, [])
    element.type.assert_not_called()  # did NOT type (static select) — no blind Enter
    element.press.assert_not_called()  # did NOT press a blind Enter


async def test_select_custom_option_async_typeahead_types_then_matches():
    """Async select (no static options, e.g. city): types to load, then
    matches the option and clicks the exact one."""
    filler = make_filler()
    element = MagicMock()
    element.click = AsyncMock()
    element.type = AsyncMock()
    element.scroll_into_view_if_needed = AsyncMock()
    # 1st (static) read is empty → types → 2nd read brings the loaded cities
    filler._visible_options = AsyncMock(
        side_effect=[[], ["Belo Horizonte, Brazil", "Recife, Brazil"]]
    )
    filler._click_option_exact = AsyncMock(return_value=True)
    filler._selected_value = AsyncMock(return_value="Belo Horizonte, Brazil")
    filler._llm_pick = AsyncMock(return_value=None)
    filler.page.keyboard = MagicMock()
    filler.page.keyboard.press = AsyncMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await filler.select_custom_option(
            element, "Where are you based?", "Belo Horizonte"
        )

    assert result is True
    element.type.assert_awaited()  # typed to load (async)
    filler._click_option_exact.assert_awaited_with("Belo Horizonte, Brazil", element, [])
    filler._llm_pick.assert_not_called()  # local match resolved it, no LLM


async def test_type_and_reload_logs_when_typing_raises(caplog):
    """Typing into an async/typeahead select can raise (element detached, overlay);
    the failure is swallowed on purpose -- we still fall through to reading the
    visible options -- but it must be logged."""
    filler = make_filler()
    element = MagicMock()
    element.type = AsyncMock(side_effect=Exception("boom"))
    with (
        patch("asyncio.sleep", new=AsyncMock()),
        patch.object(
            type(filler), "_visible_options", new=AsyncMock(return_value=["Belo Horizonte"])
        ),
        caplog.at_level(logging.DEBUG, logger=LOGGER_NAME),
    ):
        assert await filler._type_and_reload(element, "BH") == ["Belo Horizonte"]
    assert "typeahead typing failed" in caplog.text


async def test_select_custom_option_presses_escape_when_no_match():
    """select_custom_option presses Escape and logs options when no match is found."""
    filler = make_filler()
    element = MagicMock()
    element.click = AsyncMock()
    filler.page.evaluate = AsyncMock(
        return_value={"clicked": False, "options": ["São Paulo", "Rio de Janeiro"]}
    )
    filler.page.keyboard = MagicMock()
    filler.page.keyboard.press = AsyncMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await filler.select_custom_option(element, "City", "Unknown Option")

    assert result is False
    filler.page.keyboard.press.assert_called_once_with("Escape")


async def test_select_custom_option_handles_exception():
    """select_custom_option returns False instead of propagating an exception."""
    filler = make_filler()
    element = MagicMock()
    element.click = AsyncMock(side_effect=Exception("element detached"))
    filler.page.keyboard = MagicMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await filler.select_custom_option(element, "Status", "Yes")

    assert result is False


async def test_select_custom_option_snapshots_before_opening_menu():
    """select_custom_option takes the options snapshot BEFORE opening the menu, and
    passes that snapshot to _visible_options/_click_option_exact (used in Approach C's
    fallback — excludes always-mounted widgets as pollution)."""
    filler = make_filler()
    element = MagicMock()
    element.click = AsyncMock()
    element.scroll_into_view_if_needed = AsyncMock()
    filler._option_texts_snapshot = AsyncMock(return_value=["Afghanistan+93"])
    filler._visible_options = AsyncMock(return_value=["Yes", "No"])
    filler._click_option_exact = AsyncMock(return_value=True)
    filler._selected_value = AsyncMock(return_value="Yes")
    filler.page.keyboard = MagicMock()
    filler.page.keyboard.press = AsyncMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await filler.select_custom_option(element, "Status", "Yes")

    assert result is True
    filler._option_texts_snapshot.assert_awaited_once()
    filler._visible_options.assert_awaited_with(element, ["Afghanistan+93"])
    filler._click_option_exact.assert_awaited_with("Yes", element, ["Afghanistan+93"])


async def test_select_custom_option_logs_options_on_miss(caplog):
    """select_custom_option logs the available options when no match is found
    (neither local nor LLM)."""
    filler = make_filler()
    element = MagicMock()
    element.click = AsyncMock()
    element.scroll_into_view_if_needed = AsyncMock()
    filler._visible_options = AsyncMock(return_value=["Yes", "No", "Prefer not to say"])
    filler._click_option_exact = AsyncMock(return_value=False)
    filler._selected_value = AsyncMock(return_value="")
    filler._llm_pick = AsyncMock(return_value=None)
    filler.page.keyboard = MagicMock()
    filler.page.keyboard.press = AsyncMock()

    with (
        patch("asyncio.sleep", new=AsyncMock()),
        caplog.at_level(logging.WARNING, logger=LOGGER_NAME),
    ):
        result = await filler.select_custom_option(element, "Work auth", "Maybe")

    assert result is False
    assert "Yes" in caplog.text or "No" in caplog.text


async def test_select_custom_option_outer_exception_returns_false():
    """Unsuppressed exception inside select_custom_option → False (278-280)."""
    filler = make_filler()
    filler._visible_options = AsyncMock(side_effect=Exception("boom"))
    element = MagicMock()
    element.scroll_into_view_if_needed = AsyncMock()
    element.click = AsyncMock()
    with patch("asyncio.sleep", new=AsyncMock()):
        assert await filler.select_custom_option(element, "Status", "Yes") is False


# ── fill_custom_element() ───────────────────────────────────────────────────


async def test_fill_custom_element_combobox_delegates_to_select():
    """fill_custom_element with role=combobox delegates to select_custom_option."""
    filler = make_filler()
    element = MagicMock()
    element.evaluate = AsyncMock(return_value="combobox")  # role
    filler.select_custom_option = AsyncMock(return_value=True)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await filler.fill_custom_element(element, "Status", "Yes")

    assert result is True
    filler.select_custom_option.assert_awaited_once()


async def test_fill_custom_element_typeahead_types_and_clicks():
    """fill_custom_element with no role tries typeahead: type + click the suggestion."""
    filler = make_filler()
    element = MagicMock()
    element.evaluate = AsyncMock(return_value="")  # no role
    element.click = AsyncMock()
    element.type = AsyncMock()
    filler.page.evaluate = AsyncMock(return_value={"clicked": True, "options": ["Belo Horizonte"]})

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await filler.fill_custom_element(element, "City", "Belo Horizonte")

    assert result is True
    element.type.assert_called_once()


async def test_fill_custom_element_typeahead_logs_options_on_miss(caplog):
    """fill_custom_element logs the visible options when no match is found."""
    filler = make_filler()
    element = MagicMock()
    element.evaluate = AsyncMock(return_value="")  # no role
    element.click = AsyncMock()
    element.type = AsyncMock()
    filler.page.evaluate = AsyncMock(
        return_value={"clicked": False, "options": ["São Paulo", "Rio de Janeiro"]}
    )

    with (
        patch("asyncio.sleep", new=AsyncMock()),
        caplog.at_level(logging.WARNING, logger=LOGGER_NAME),
    ):
        result = await filler.fill_custom_element(element, "City", "Belo Horizonte")

    assert result is False
    assert "São Paulo" in caplog.text or "Rio de Janeiro" in caplog.text


async def test_fill_custom_element_typeahead_exception_returns_false():
    filler = make_filler()
    element = MagicMock()
    element.evaluate = AsyncMock(return_value="")  # empty role, no select class
    element.click = AsyncMock(side_effect=Exception("boom"))
    with patch("asyncio.sleep", new=AsyncMock()):
        assert await filler.fill_custom_element(element, "City", "BH") is False


# ── is_custom_combobox() ────────────────────────────────────────────────────


async def test_is_custom_combobox_true_for_role_combobox():
    filler = make_filler()
    field = MagicMock()
    field.evaluate = AsyncMock(return_value=True)
    assert await filler.is_custom_combobox(field) is True


async def test_is_custom_combobox_false_for_native_input():
    filler = make_filler()
    field = MagicMock()
    field.evaluate = AsyncMock(return_value=False)
    assert await filler.is_custom_combobox(field) is False


# ── _choose_and_click: clicks but doesn't verify → False (294->296) ─────────


async def test_choose_and_click_false_when_value_not_verified():
    filler = make_filler()
    filler._click_option_exact = AsyncMock(return_value=True)
    filler._selected_value = AsyncMock(return_value="")  # selection not confirmed
    filler._llm_pick = AsyncMock(return_value=None)
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await filler._choose_and_click(MagicMock(), "Status", "Yes", ["Yes", "No"])
    assert result is False


# ── helpers de escopo (_option_texts_snapshot, _field_id, _scoped_locator) ──


async def test_option_texts_snapshot_returns_cleaned_texts():
    filler = make_filler()
    loc = MagicMock()
    loc.all_inner_texts = AsyncMock(return_value=["Afghanistan+93", "  Albania+355  ", "   "])
    filler.page.locator = MagicMock(return_value=loc)
    assert await filler._option_texts_snapshot() == ["Afghanistan+93", "Albania+355"]


async def test_option_texts_snapshot_empty_on_exception():
    filler = make_filler()
    filler.page.locator = MagicMock(side_effect=Exception("boom"))
    assert await filler._option_texts_snapshot() == []


async def test_field_id_returns_attribute():
    filler = make_filler()
    element = MagicMock()
    element.get_attribute = AsyncMock(return_value="question_123")
    assert await filler._field_id(element) == "question_123"


async def test_field_id_none_when_missing():
    filler = make_filler()
    element = MagicMock()
    element.get_attribute = AsyncMock(return_value=None)
    assert await filler._field_id(element) is None


async def test_field_id_none_on_exception():
    """Mock element with no get_attribute configured (plain MagicMock) raises
    TypeError when awaited — treated as 'no id', falls to the broad fallback."""
    filler = make_filler()
    element = MagicMock()
    assert await filler._field_id(element) is None


async def test_scoped_locator_returns_locator_when_matches_found():
    filler = make_filler()
    element = MagicMock()
    element.get_attribute = AsyncMock(return_value="question_123")
    scoped = MagicMock()
    scoped.count = AsyncMock(return_value=2)
    filler.page.locator = MagicMock(return_value=scoped)
    result = await filler._scoped_locator(element)
    assert result is scoped
    filler.page.locator.assert_called_with('[id^="react-select-question_123-option"]')


async def test_scoped_locator_none_when_no_field_id():
    filler = make_filler()
    element = MagicMock()
    element.get_attribute = AsyncMock(return_value=None)
    filler.page.locator = MagicMock()
    result = await filler._scoped_locator(element)
    assert result is None
    filler.page.locator.assert_not_called()  # doesn't even try the locator without an id


async def test_scoped_locator_none_when_zero_matches():
    filler = make_filler()
    element = MagicMock()
    element.get_attribute = AsyncMock(return_value="question_123")
    scoped = MagicMock()
    scoped.count = AsyncMock(return_value=0)
    filler.page.locator = MagicMock(return_value=scoped)
    assert await filler._scoped_locator(element) is None


async def test_scoped_locator_none_on_count_exception(caplog):
    filler = make_filler()
    element = MagicMock()
    element.get_attribute = AsyncMock(return_value="question_123")
    scoped = MagicMock()
    scoped.count = AsyncMock(side_effect=Exception("boom"))
    filler.page.locator = MagicMock(return_value=scoped)
    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        assert await filler._scoped_locator(element) is None
    assert "scoped locator lookup failed" in caplog.text


async def test_scoped_locator_none_on_locator_exception():
    filler = make_filler()
    element = MagicMock()
    element.get_attribute = AsyncMock(return_value="question_123")
    filler.page.locator = MagicMock(side_effect=Exception("malformed selector"))
    assert await filler._scoped_locator(element) is None


# ── _visible_options (real) ─────────────────────────────────────────────────


async def test_visible_options_returns_normalized_texts():
    filler = make_filler()
    element = MagicMock()  # no get_attribute configured -> _field_id returns None
    loc = MagicMock()
    loc.first.wait_for = AsyncMock()
    loc.all_inner_texts = AsyncMock(return_value=["Yes", "  No  ", "   "])
    filler.page.locator = MagicMock(return_value=loc)
    assert await filler._visible_options(element) == ["Yes", "No"]


async def test_visible_options_empty_when_wait_times_out():
    filler = make_filler()
    element = MagicMock()
    loc = MagicMock()
    loc.first.wait_for = AsyncMock(side_effect=Exception("timeout"))
    filler.page.locator = MagicMock(return_value=loc)
    assert await filler._visible_options(element) == []


async def test_visible_options_empty_on_locator_exception():
    filler = make_filler()
    element = MagicMock()
    filler.page.locator = MagicMock(side_effect=Exception("boom"))
    assert await filler._visible_options(element) == []


async def test_visible_options_uses_id_scoped_locator_when_available():
    """Approach A: locator scoped by the field's id finds options -> uses it directly,
    ignoring pollution from the broad selector (e.g. the phone's country list)."""
    filler = make_filler()
    element = MagicMock()
    element.get_attribute = AsyncMock(return_value="question_123")
    scoped = MagicMock()
    scoped.count = AsyncMock(return_value=2)
    scoped.all_inner_texts = AsyncMock(return_value=["Yes", "No"])
    filler.page.locator = MagicMock(return_value=scoped)
    assert await filler._visible_options(element) == ["Yes", "No"]


async def test_visible_options_falls_back_to_diff_when_no_scoped_match():
    """Approach C: with no scoped locator (id absent), falls back to the broad selector
    and excludes texts already present BEFORE the menu was opened (pollution from
    always-mounted widgets)."""
    filler = make_filler()
    element = MagicMock()
    element.get_attribute = AsyncMock(return_value=None)  # no id -> no Approach A
    broad = MagicMock()
    broad.first.wait_for = AsyncMock()
    broad.all_inner_texts = AsyncMock(return_value=["Afghanistan+93", "Albania+355", "Yes", "No"])
    filler.page.locator = MagicMock(return_value=broad)
    before_texts = ["Afghanistan+93", "Albania+355"]  # already existed before opening the menu
    assert await filler._visible_options(element, before_texts) == ["Yes", "No"]


# ── _click_option_exact (real) ──────────────────────────────────────────────


async def test_click_option_exact_clicks_matching_option():
    filler = make_filler()
    element = MagicMock()
    opt0 = MagicMock()
    opt0.inner_text = AsyncMock(return_value="No")
    opt1 = MagicMock()
    opt1.inner_text = AsyncMock(return_value="Yes")
    opt1.click = AsyncMock()
    objs = {0: opt0, 1: opt1}
    loc = MagicMock()
    loc.count = AsyncMock(return_value=2)
    loc.nth = MagicMock(side_effect=lambda i: objs[i])
    filler.page.locator = MagicMock(return_value=loc)
    assert await filler._click_option_exact("Yes", element) is True
    opt1.click.assert_awaited_once()


async def test_click_option_exact_returns_false_when_no_match():
    filler = make_filler()
    element = MagicMock()
    opt = MagicMock()
    opt.inner_text = AsyncMock(return_value="Maybe")
    loc = MagicMock()
    loc.count = AsyncMock(return_value=1)
    loc.nth = MagicMock(return_value=opt)
    filler.page.locator = MagicMock(return_value=loc)
    assert await filler._click_option_exact("Yes", element) is False


async def test_click_option_exact_returns_false_on_exception():
    filler = make_filler()
    element = MagicMock()
    filler.page.locator = MagicMock(side_effect=Exception("boom"))
    assert await filler._click_option_exact("Yes", element) is False


async def test_click_option_exact_uses_id_scoped_locator_when_available():
    filler = make_filler()
    element = MagicMock()
    element.get_attribute = AsyncMock(return_value="question_123")
    opt0 = MagicMock()
    opt0.inner_text = AsyncMock(return_value="No")
    opt1 = MagicMock()
    opt1.inner_text = AsyncMock(return_value="Yes")
    opt1.click = AsyncMock()
    scoped = MagicMock()
    scoped.count = AsyncMock(return_value=2)
    scoped.nth = MagicMock(side_effect=lambda i: [opt0, opt1][i])
    filler.page.locator = MagicMock(return_value=scoped)
    assert await filler._click_option_exact("Yes", element) is True
    opt1.click.assert_awaited_once()


async def test_click_option_exact_falls_back_and_ignores_pollution():
    """Approach C: with no scoped locator, uses the broad selector normally — excluding
    before_texts does not block the real match (it would only be ignored if the
    pollution TEXT were identical to the answer, which doesn't happen in practice:
    countries vs Yes/No)."""
    filler = make_filler()
    element = MagicMock()
    element.get_attribute = AsyncMock(return_value=None)
    country = MagicMock()
    country.inner_text = AsyncMock(return_value="Afghanistan+93")
    real = MagicMock()
    real.inner_text = AsyncMock(return_value="Yes")
    real.click = AsyncMock()
    loc = MagicMock()
    loc.count = AsyncMock(return_value=2)
    loc.nth = MagicMock(side_effect=lambda i: [country, real][i])
    filler.page.locator = MagicMock(return_value=loc)
    result = await filler._click_option_exact("Yes", element, ["Afghanistan+93"])
    assert result is True
    real.click.assert_awaited_once()


# ── _llm_pick (real) ────────────────────────────────────────────────────────


async def test_llm_pick_returns_choice():
    filler = make_filler()
    filler.config = {"llm_model": "m"}
    with (
        patch(
            "gauntler.application.answers.option_matcher.pick_option_with_llm",
            new=AsyncMock(return_value="Native"),
        ),
        patch(
            "gauntler.application.appliers.custom_dropdown.make_caller",
            return_value=AsyncMock(),
        ),
    ):
        result = await filler._llm_pick("English", "Fluent", ["Native", "Basic"])
    assert result == "Native"


async def test_llm_pick_returns_none_without_options():
    filler = make_filler()
    assert await filler._llm_pick("English", "Fluent", []) is None


async def test_llm_pick_returns_none_on_exception():
    filler = make_filler()
    with patch(
        "gauntler.application.appliers.custom_dropdown.make_caller",
        side_effect=Exception("boom"),
    ):
        assert await filler._llm_pick("English", "Fluent", ["Native"]) is None


# ── _selected_value (real) ──────────────────────────────────────────────────


async def test_selected_value_reads_single_value():
    filler = make_filler()
    element = MagicMock()
    element.evaluate = AsyncMock(return_value="Yes")
    assert await filler._selected_value(element) == "Yes"


async def test_selected_value_empty_on_exception():
    filler = make_filler()
    element = MagicMock()
    element.evaluate = AsyncMock(side_effect=Exception("boom"))
    assert await filler._selected_value(element) == ""
