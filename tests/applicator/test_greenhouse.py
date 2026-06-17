from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeout

from candidatador.applicator.greenhouse import GreenhouseApplier


def make_label_locator(field_mock=None):
    """Cria um mock de Locator do Playwright que retorna field_mock via element_handle()."""
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
    page.inner_text = AsyncMock(return_value="")  # sem confirmação por padrão
    page.get_by_label = MagicMock(return_value=make_label_locator(None))  # padrão: sem match
    page.evaluate = AsyncMock(return_value=None)
    config = {}
    profile = {}
    return GreenhouseApplier(page, config, profile)


def make_evaluate(tag, combobox=False, selected=""):
    """Stub de field.evaluate robusto à ordem/contagem de chamadas: devolve o valor
    selecionado (single-value), o flag de combobox e o tag conforme o JS chamado."""

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
    """fill() é chamado via get_by_label (estratégia 1)."""
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
    """QUALITY-02: campo <select> é resolvido via select_option (por label), não fill."""
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
    """fill() é chamado em campos textarea via get_by_label."""
    applier = make_applier()

    field = MagicMock()
    field.evaluate = make_evaluate("textarea")
    field.fill = AsyncMock()

    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))

    with patch("asyncio.sleep", new=AsyncMock()):
        await applier.fill_form({"Bio": "Senior engineer"}, cv_path="")

    field.fill.assert_called_once_with("Senior engineer")


async def test_fill_form_skips_when_no_field_found():
    """Se get_by_label e JS fallback não acham o campo, nenhum fill é chamado."""
    applier = make_applier()
    # get_by_label retorna locator sem match (já é o default de make_applier)
    # evaluate retorna None (sem for_id) — já é default

    field = MagicMock()
    field.fill = AsyncMock()

    await applier.fill_form({"Full Name": "Alberto"}, cv_path="")
    field.fill.assert_not_called()


async def test_fill_form_uploads_cv():
    """set_input_files é chamado no locator de file input com o cv_path."""
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
    """Exception em um campo não impede os outros de serem preenchidos."""
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
    """submit() → 'submitted' quando a página confirma o envio."""
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
    """RELIABILITY-01: clicou mas sem marcador de confirmação → 'unverified'."""
    applier = make_applier("https://boards.greenhouse.io/stripe/jobs/123")

    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=btn)
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="Full Name Email Submit Application")

    result = await applier.submit()
    assert result == "unverified"


async def test_submit_no_button_returns_failed():
    """submit() → 'failed' quando não acha o botão de enviar."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)

    result = await applier.submit()
    assert result == "failed"


async def test_submit_exception_returns_failed():
    """submit() → 'failed' quando o clique levanta exceção."""
    applier = make_applier()

    btn = MagicMock()
    btn.click = AsyncMock(side_effect=Exception("click failed"))
    applier.page.query_selector = AsyncMock(return_value=btn)

    result = await applier.submit()
    assert result == "failed"


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


# ── _find_field() ─────────────────────────────────────────────────────────────


async def test_find_field_uses_get_by_label_exact_first():
    """_find_field tenta get_by_label exact=True antes de exact=False."""
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
    assert call_args[0] is True  # tentou exact primeiro


async def test_find_field_falls_back_to_inexact():
    """_find_field usa exact=False quando exact=True não encontra."""
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
    """_find_field usa JS para normalizar label e buscar por for-id quando get_by_label falha."""
    applier = make_applier()
    # get_by_label não encontra nada
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    # JS retorna um for_id
    applier.page.evaluate = AsyncMock(return_value="phone_field")
    field = MagicMock()
    applier.page.query_selector = AsyncMock(return_value=field)

    result = await applier._find_field("Phone")
    assert result is field
    applier.page.query_selector.assert_called_once_with("#phone_field")


async def test_find_field_aria_label_strategy():
    """_find_field usa [aria-label] como última estratégia."""
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value=None)  # JS não acha for_id
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
    """_find_field retorna None quando nenhuma estratégia encontra o campo."""
    applier = make_applier()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value=None)
    applier.page.query_selector = AsyncMock(return_value=None)

    result = await applier._find_field("Unknown Label XYZ")
    assert result is None


# ── fill_form() status dict ────────────────────────────────────────────────────


async def test_fill_form_returns_status_dict():
    """fill_form retorna dict com status por campo."""
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
        result = await applier.fill_form({"Nome": "Alberto"}, cv_path="")

    assert isinstance(result, dict)
    assert result.get("Nome") == "filled"


async def test_fill_form_skips_empty_answer():
    """fill_form marca como 'skipped' campos com resposta vazia."""
    applier = make_applier()
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"Campo": ""}, cv_path="")
    assert result.get("Campo") == "skipped"


async def test_fill_form_skips_skip_sentinel():
    """fill_form marca como 'skipped' campos com __SKIP__."""
    applier = make_applier()
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"Attach": "__SKIP__"}, cv_path="")
    assert result.get("Attach") == "skipped"


async def test_fill_form_marks_failed_when_field_not_found():
    """fill_form retorna 'failed:not_found' quando campo não é localizado."""
    applier = make_applier()
    # Todas estratégias retornam None
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(None))
    applier.page.evaluate = AsyncMock(return_value=None)
    applier.page.query_selector = AsyncMock(return_value=None)
    applier.page.locator = MagicMock(
        return_value=MagicMock(first=MagicMock(count=AsyncMock(return_value=0)))
    )

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"Campo Inexistente": "valor"}, cv_path="")

    assert result.get("Campo Inexistente") == "failed:not_found"


# ── _upload_cv() ──────────────────────────────────────────────────────────────


async def test_upload_cv_skips_when_no_path():
    """_upload_cv retorna 'skipped' quando cv_path está vazio."""
    applier = make_applier()
    result = await applier._upload_cv("")
    assert result == "skipped"


async def test_upload_cv_falls_back_to_query_selector():
    """_upload_cv usa query_selector quando locator.first.count retorna 0."""
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
    """_upload_cv retorna 'failed:no_file_input' quando não há input de arquivo."""
    applier = make_applier()
    empty_first = MagicMock()
    empty_first.count = AsyncMock(return_value=0)
    applier.page.locator = MagicMock(return_value=MagicMock(first=empty_first))
    applier.page.query_selector = AsyncMock(return_value=None)

    result = await applier._upload_cv("/path/cv.pdf")
    assert result == "failed:no_file_input"


# ── _select_custom_option() ───────────────────────────────────────────────────


async def test_select_custom_option_clicks_and_selects():
    """_select_custom_option: match local na opção estática, clica a exata e VERIFICA."""
    applier = make_applier()
    element = MagicMock()
    element.click = AsyncMock()
    element.type = AsyncMock()
    element.press = AsyncMock()
    element.scroll_into_view_if_needed = AsyncMock()
    applier._visible_options = AsyncMock(return_value=["Yes", "No"])
    applier._click_option_exact = AsyncMock(return_value=True)
    applier._selected_value = AsyncMock(return_value="Yes")
    applier.page.keyboard = MagicMock()
    applier.page.keyboard.press = AsyncMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._select_custom_option(element, "Status", "Yes")

    assert result is True
    applier._click_option_exact.assert_awaited_with("Yes")  # clicou a opção exata
    applier.page.keyboard.press.assert_not_called()


async def test_select_custom_option_uses_llm_for_descriptive_options():
    """Quando o match local falha (opções em frase) o LLM escolhe entre as opções REAIS,
    SEM digitar (regressão: digitar 'Fluent' filtraria p/ 'not able to speak fluently' e
    o Enter cego pegaria a negativa)."""
    applier = make_applier()
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
    applier._visible_options = AsyncMock(return_value=cefr)
    applier._click_option_exact = AsyncMock(return_value=True)
    applier._selected_value = AsyncMock(return_value="Native or bilingual proficiency")
    applier._llm_pick = AsyncMock(return_value="Native or bilingual proficiency")
    applier.page.keyboard = MagicMock()
    applier.page.keyboard.press = AsyncMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._select_custom_option(element, "English level", "Fluent")

    assert result is True
    applier._llm_pick.assert_awaited_once()
    applier._click_option_exact.assert_awaited_with("Native or bilingual proficiency")
    element.type.assert_not_called()  # NÃO digitou (select estático) — sem Enter cego
    element.press.assert_not_called()  # NÃO deu Enter cego


async def test_select_custom_option_async_typeahead_types_then_matches():
    """Select async (sem opções estáticas, ex: cidade): digita p/ carregar, então
    casa a opção e clica a exata."""
    applier = make_applier()
    element = MagicMock()
    element.click = AsyncMock()
    element.type = AsyncMock()
    element.scroll_into_view_if_needed = AsyncMock()
    # 1ª leitura (estática) vazia → digita → 2ª leitura traz as cidades carregadas
    applier._visible_options = AsyncMock(
        side_effect=[[], ["Belo Horizonte, Brazil", "Recife, Brazil"]]
    )
    applier._click_option_exact = AsyncMock(return_value=True)
    applier._selected_value = AsyncMock(return_value="Belo Horizonte, Brazil")
    applier._llm_pick = AsyncMock(return_value=None)
    applier.page.keyboard = MagicMock()
    applier.page.keyboard.press = AsyncMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._select_custom_option(
            element, "Where are you based?", "Belo Horizonte"
        )

    assert result is True
    element.type.assert_awaited()  # digitou para carregar (async)
    applier._click_option_exact.assert_awaited_with("Belo Horizonte, Brazil")
    applier._llm_pick.assert_not_called()  # match local resolveu, sem LLM


async def test_select_custom_option_presses_escape_when_no_match():
    """_select_custom_option pressiona Escape e loga opções quando não acha match."""
    applier = make_applier()
    element = MagicMock()
    element.click = AsyncMock()
    applier.page.evaluate = AsyncMock(
        return_value={"clicked": False, "options": ["São Paulo", "Rio de Janeiro"]}
    )
    applier.page.keyboard = MagicMock()
    applier.page.keyboard.press = AsyncMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._select_custom_option(element, "City", "Unknown Option")

    assert result is False
    applier.page.keyboard.press.assert_called_once_with("Escape")


async def test_select_custom_option_handles_exception():
    """_select_custom_option retorna False em vez de propagar exceção."""
    applier = make_applier()
    element = MagicMock()
    element.click = AsyncMock(side_effect=Exception("element detached"))
    applier.page.keyboard = MagicMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._select_custom_option(element, "Status", "Yes")

    assert result is False


# ── _fill_custom_element() ────────────────────────────────────────────────────


async def test_fill_custom_element_combobox_delegates_to_select():
    """_fill_custom_element com role=combobox delega para _select_custom_option."""
    applier = make_applier()
    element = MagicMock()
    element.evaluate = AsyncMock(return_value="combobox")  # role
    applier._select_custom_option = AsyncMock(return_value=True)

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._fill_custom_element(element, "Status", "Yes")

    assert result is True
    applier._select_custom_option.assert_awaited_once()


async def test_fill_custom_element_typeahead_types_and_clicks():
    """_fill_custom_element sem role tenta typeahead: type + clica na sugestão."""
    applier = make_applier()
    element = MagicMock()
    element.evaluate = AsyncMock(return_value="")  # sem role
    element.click = AsyncMock()
    element.type = AsyncMock()
    applier.page.evaluate = AsyncMock(return_value={"clicked": True, "options": ["Belo Horizonte"]})

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier._fill_custom_element(element, "City", "Belo Horizonte")

    assert result is True
    element.type.assert_called_once()


async def test_fill_custom_element_typeahead_logs_options_on_miss(caplog):
    """_fill_custom_element loga as opções visíveis quando não encontra match."""
    import logging

    applier = make_applier()
    element = MagicMock()
    element.evaluate = AsyncMock(return_value="")  # sem role
    element.click = AsyncMock()
    element.type = AsyncMock()
    applier.page.evaluate = AsyncMock(
        return_value={"clicked": False, "options": ["São Paulo", "Rio de Janeiro"]}
    )

    with (
        patch("asyncio.sleep", new=AsyncMock()),
        caplog.at_level(logging.WARNING, logger="candidatador.applicator.greenhouse"),
    ):
        result = await applier._fill_custom_element(element, "City", "Belo Horizonte")

    assert result is False
    assert "São Paulo" in caplog.text or "Rio de Janeiro" in caplog.text


async def test_select_custom_option_logs_options_on_miss(caplog):
    """_select_custom_option loga as opções disponíveis quando não encontra match
    (nem local nem LLM)."""
    import logging

    applier = make_applier()
    element = MagicMock()
    element.click = AsyncMock()
    element.scroll_into_view_if_needed = AsyncMock()
    applier._visible_options = AsyncMock(return_value=["Yes", "No", "Prefer not to say"])
    applier._click_option_exact = AsyncMock(return_value=False)
    applier._selected_value = AsyncMock(return_value="")
    applier._llm_pick = AsyncMock(return_value=None)
    applier.page.keyboard = MagicMock()
    applier.page.keyboard.press = AsyncMock()

    with (
        patch("asyncio.sleep", new=AsyncMock()),
        caplog.at_level(logging.WARNING, logger="candidatador.applicator.greenhouse"),
    ):
        result = await applier._select_custom_option(element, "Work auth", "Maybe")

    assert result is False
    assert "Yes" in caplog.text or "No" in caplog.text


# ── submit() novos comportamentos ─────────────────────────────────────────────


async def test_submit_detects_form_still_visible_after_click():
    """submit() retorna 'failed:validation_errors:...' quando form ainda está visível."""
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
            return btn  # primeiro call: encontra o botão
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
    """submit() loga aviso quando há campos obrigatórios vazios antes de submeter."""
    import logging

    applier = make_applier()
    btn = MagicMock()
    btn.click = AsyncMock()
    applier.page.wait_for_load_state = AsyncMock()
    applier.page.inner_text = AsyncMock(return_value="thank you for applying")
    applier.page.query_selector = AsyncMock(return_value=btn)
    # evaluate: (1) empty required fields presentes, (2) form not visible after submit
    applier.page.evaluate = AsyncMock(side_effect=[["First Name *"], False, []])

    with caplog.at_level(logging.WARNING, logger="candidatador.applicator.greenhouse"):
        await applier.submit()

    assert "First Name" in caplog.text


# ── logging ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_greenhouse_detect_logs_match(caplog):
    import logging

    applier = make_applier("https://boards.greenhouse.io/stripe/jobs/1")
    with caplog.at_level(logging.DEBUG, logger="candidatador.applicator.greenhouse"):
        await applier.detect()
    assert "detect: greenhouse" in caplog.text


@pytest.mark.asyncio
async def test_greenhouse_submit_logs_outcome(caplog):
    import logging

    applier = make_applier("https://boards.greenhouse.io/stripe/jobs/1")
    submit_btn = AsyncMock()
    applier.page.query_selector = AsyncMock(return_value=submit_btn)
    applier.page.wait_for_load_state = AsyncMock()
    # simula página de confirmação
    applier.page.inner_text = AsyncMock(return_value="application submitted successfully")
    applier.page.url = "https://boards.greenhouse.io/confirmation"

    with caplog.at_level(logging.INFO, logger="candidatador.applicator.greenhouse"):
        outcome = await applier.submit()

    assert "submit" in caplog.text
    assert outcome in ("submitted", "unverified")


# ── extract_fields: exclui campos de upload-alternativo ───────────────────────


async def test_extract_fields_excludes_upload_alternatives():
    """Attach/Anexar/Enter manually/Informe manualmente são da área de upload de CV
    (tratada por _upload_cv) — não devem ir pro LLM como campos de texto."""
    applier = make_applier()
    applier.page.query_selector = AsyncMock(return_value=None)
    labels = []
    for text in [
        "Attach",
        "Anexar",
        "Enter manually",
        "Informe manualmente",
        "First Name",
        "Telefone",
    ]:
        m = MagicMock()
        m.inner_text = AsyncMock(return_value=text)
        labels.append(m)
    applier.page.query_selector_all = AsyncMock(return_value=labels)

    fields = await applier.extract_fields()
    for excluded in ("Attach", "Anexar", "Enter manually", "Informe manualmente"):
        assert excluded not in fields
    assert "First Name" in fields
    assert "Telefone" in fields


# ── fill_form: react-select (input role=combobox) ─────────────────────────────


async def test_fill_form_routes_combobox_input_to_custom_dropdown():
    """react-select: <input role=combobox> deve ir pro handler de dropdown custom,
    não ser tratado como text input (senão digita no busca e mente 'filled')."""
    applier = make_applier()
    field = MagicMock()
    field.evaluate = make_evaluate("input", combobox=True)  # tagName + combobox-check
    field.fill = AsyncMock()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))
    applier.page.locator = MagicMock(
        return_value=MagicMock(first=MagicMock(count=AsyncMock(return_value=0)))
    )
    applier._select_custom_option = AsyncMock(return_value=True)  # handler de dropdown

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form(
            {"Are you able to work from the office?": "Yes"}, cv_path=""
        )

    assert result["Are you able to work from the office?"] == "filled"
    applier._select_custom_option.assert_awaited_once()  # roteou pro handler de dropdown
    field.fill.assert_not_called()  # NÃO tratou como text input


async def test_fill_form_combobox_no_match_marks_failed_not_filled():
    """Se a opção não é encontrada no react-select, status é failed — nunca 'filled'."""
    applier = make_applier()
    field = MagicMock()
    # combobox, mas single-value continua vazio → nada foi selecionado → failed
    field.evaluate = make_evaluate("input", combobox=True, selected="")
    field.click = AsyncMock()
    field.type = AsyncMock()
    field.press = AsyncMock()
    field.fill = AsyncMock()
    applier.page.get_by_label = MagicMock(return_value=make_label_locator(field))
    applier.page.locator = MagicMock(
        return_value=MagicMock(first=MagicMock(count=AsyncMock(return_value=0)))
    )
    applier.page.evaluate = AsyncMock(return_value=False)  # nenhuma opção casou
    applier.page.keyboard = MagicMock()
    applier.page.keyboard.press = AsyncMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await applier.fill_form({"English level": "Fluent"}, cv_path="")

    assert result["English level"].startswith("failed")
