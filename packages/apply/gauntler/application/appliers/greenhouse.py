import asyncio
import contextlib
import re
from typing import Any

from gauntler.application.appliers.base import BaseApplier
from gauntler.core.log import get_logger
from playwright.async_api import TimeoutError as PlaywrightTimeout

logger = get_logger(__name__)

# Sentinelas de resposta que não devem ser preenchidas no formulário.
_SKIP_SENTINELS = {"__SKIP__", "__MANUAL_UPLOAD_REQUIRED__", "__NEEDS_REVIEW__"}

# Labels da área de upload de CV/currículo — o anexo é tratado por _upload_cv, então
# não devem ir pro LLM como campos de texto (senão recebem resposta-lixo).
_UPLOAD_LABELS = {
    "resume/cv",
    "cover letter",
    "attach",
    "anexar",
    "enter manually",
    "informe manualmente",
}


def _is_skip(answer: str) -> bool:
    return not answer or answer in _SKIP_SENTINELS


def _log_fill_stats(status: dict[str, str]) -> None:
    filled = sum(1 for s in status.values() if s == "filled")
    failed = [label for label, s in status.items() if s.startswith("failed")]
    skipped = sum(1 for s in status.values() if s == "skipped")
    logger.info("fill_form: %d filled, %d failed, %d skipped", filled, len(failed), skipped)
    if failed:
        logger.warning("fill_form: campos com falha: %s", failed)


class GreenhouseApplier(BaseApplier):
    _OPTION_SELECTOR = '.select__option, [role="option"], [role="listbox"] li'

    async def detect(self) -> bool:
        match = "greenhouse.io" in self.page.url or "boards.greenhouse.io" in self.page.url
        if match:
            logger.debug("detect: greenhouse ✓ (%s)", self.page.url)
        return match

    async def extract_fields(self) -> list[str]:
        await self._open_application()
        from gauntler.application.appliers.base import _query_labels_with_fallback

        label_els = await _query_labels_with_fallback(
            self.page,
            ["label, .field-label", ".application-question label", "[data-field-label]"],
        )
        labels = []
        for el in label_els:
            text = (await el.inner_text()).strip()
            if text and text.lower() not in _UPLOAD_LABELS:
                labels.append(text)
        logger.debug("extract_fields: %d campos", len(labels))
        return labels

    async def _open_application(self) -> None:
        """Clica no botão 'Apply' quando o formulário ainda não está aberto."""
        try:
            apply_btn = await self.page.query_selector(
                "a#apply, button#apply, a[data-greenhouse-job-board-apply]"
            )
            if apply_btn:
                await apply_btn.click()
                await self.page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            pass

    async def fill_form(self, answers: dict[str, str], cv_path: str) -> dict[str, str]:
        """Preenche o formulário. Devolve {label: "filled"|"skipped"|"failed:<motivo>"}.
        Nunca levanta — falhas vão no retorno e no log."""
        logger.info("fill_form: start (%d respostas)", len(answers))
        status = {label: await self._fill_one(label, answer) for label, answer in answers.items()}
        if cv_path:
            status["__cv__"] = await self._upload_cv(cv_path)
        _log_fill_stats(status)
        return status

    async def _fill_one(self, label_text: str, answer: str) -> str:
        if _is_skip(answer):
            return "skipped"
        try:
            field = await self._find_field(label_text)
            if field is None:
                logger.debug("fill_form: campo não encontrado — '%s'", label_text)
                return "failed:not_found"

            if await self._is_custom_combobox(field):
                ok = await self._select_custom_option(field, label_text, answer)
                return "filled" if ok else "failed:custom_dropdown"

            tag = await field.evaluate("el => el.tagName.toLowerCase()")
            if tag in ("input", "textarea", "select"):
                from gauntler.application.appliers.base import _fill_field

                await _fill_field(field, answer)
                await asyncio.sleep(0.2)
                return "filled"

            ok = await self._fill_custom_element(field, label_text, answer)
            return "filled" if ok else "failed:custom_element_unsupported"
        except Exception as e:
            logger.debug("fill_form: exception em '%s': %s", label_text, e)
            return f"failed:{type(e).__name__}"

    async def _is_custom_combobox(self, field: Any) -> bool:
        """react-select expõe um <input role=combobox aria-haspopup class=select__input>.
        Tratá-lo como text input só DIGITA no campo de busca sem selecionar a opção — e
        ainda reportaria 'filled' (falso positivo). Por isso roteamos para o handler
        de dropdown custom em vez do _fill_field nativo."""
        return bool(
            await field.evaluate(
                "el => el.getAttribute('role') === 'combobox'"
                " || el.getAttribute('aria-haspopup') === 'true'"
                " || (el.className || '').toLowerCase().includes('select__input')"
            )
        )

    async def _find_field(self, label_text: str) -> Any:
        """Localiza o input associado a um label, em cascata. Devolve o ElementHandle
        ou None."""
        # 1) get_by_label (resolve for/aria-label/labelledby + normaliza texto)
        for exact in (True, False):
            locator = self.page.get_by_label(label_text, exact=exact)
            if await locator.count() > 0:
                return await locator.first.element_handle()

        # 2) JS: normaliza o label (strip *, &nbsp;, espaços) e pega o atributo `for`
        for_id = await self.page.evaluate(
            """(text) => {
                const target = text.replace(/[*\\u00a0]+/g, ' ').replace(/\\s+/g, ' ').trim().toLowerCase();
                for (const l of document.querySelectorAll('label')) {
                    const clean = l.innerText.replace(/[*\\u00a0]+/g, ' ').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (clean === target || clean.startsWith(target)) return l.getAttribute('for');
                }
                return null;
            }""",
            label_text,
        )
        if for_id:
            el = await self.page.query_selector(f"#{for_id}")
            if el:
                return el

        # 3) aria-label direto
        escaped = label_text.replace("'", "\\'")
        return await self.page.query_selector(f"[aria-label='{escaped}']")

    async def _fill_custom_element(self, element: Any, label_text: str, answer: str) -> bool:
        """Trata elementos não-nativos: dropdowns custom (role=combobox/listbox) e
        typeaheads (autocomplete). True se conseguiu preencher."""
        if await self._looks_like_dropdown(element):
            return await self._select_custom_option(element, label_text, answer)
        return await self._try_typeahead(element, label_text, answer)

    async def _looks_like_dropdown(self, element: Any) -> bool:
        role = await element.evaluate(
            "el => el.getAttribute('role') || el.getAttribute('aria-haspopup') || ''"
        )
        if role in ("combobox", "listbox", "button"):
            return True
        return bool(
            await element.evaluate(
                "el => el.classList.toString().toLowerCase().includes('select')"
                " || el.classList.toString().toLowerCase().includes('dropdown')"
            )
        )

    async def _try_typeahead(self, element: Any, label_text: str, answer: str) -> bool:
        """Digita no campo e clica na primeira sugestão que contém a resposta."""
        try:
            await element.click()
            await element.type(answer, delay=50)
            await asyncio.sleep(0.6)
            result = await self.page.evaluate(
                """(answer) => {
                    const a = answer.toLowerCase().trim();
                    const selectors = [
                        '[role="option"]', '[role="listbox"] li',
                        '.autocomplete-suggestion', '.dropdown-item',
                        'ul li', '[data-testid*="option"]',
                    ];
                    const visible = [];
                    for (const sel of selectors) {
                        for (const el of document.querySelectorAll(sel)) {
                            const t = el.innerText.trim();
                            if (t) visible.push(t);
                            if (t.toLowerCase().includes(a)) {
                                el.click();
                                return {clicked: true, options: visible};
                            }
                        }
                    }
                    return {clicked: false, options: visible};
                }""",
                answer,
            )
            if result.get("clicked"):
                return True
            logger.warning(
                "_fill_custom_element typeahead: '%s' não achou '%s'. Opções visíveis: %s",
                label_text,
                answer,
                result.get("options") or "(nenhuma)",
            )
            return False
        except Exception as e:
            logger.warning("_fill_custom_element typeahead: '%s' exception — %s", label_text, e)
            return False

    async def _select_custom_option(self, element: Any, label_text: str, answer: str) -> bool:
        """Seleciona uma opção num react-select escolhendo SEMPRE pelo TEXTO REAL da
        opção (match local ou LLM) e clicando a opção exata, com verificação via
        .select__single-value. NUNCA dá Enter cego — na lista filtrada o Enter pegaria
        a opção destacada, que pode ser a errada (digitar 'Fluent' filtra para 'not
        able to speak fluently' e o Enter pegaria a negativa). Selects estáticos são
        escolhidos pela lista completa sem digitar; só digita quando não há opções
        estáticas (select async/typeahead que carrega ao digitar)."""
        try:
            await self._open_menu(element)
            options = await self._visible_options() or await self._type_and_reload(element, answer)
            if options and await self._choose_and_click(element, label_text, answer, options):
                return True

            logger.warning(
                "_select_custom_option: '%s' não selecionou '%s'. Opções: %s",
                label_text,
                answer,
                options or "(nenhuma — dropdown não abriu/carregou?)",
            )
            with contextlib.suppress(Exception):
                await self.page.keyboard.press("Escape")
            return False
        except Exception as e:
            logger.warning("_select_custom_option: '%s' exception — %s", label_text, e)
            return False

    async def _option_texts_snapshot(self) -> list[str]:
        """Textos de TODAS as opções que já batem com _OPTION_SELECTOR ANTES de abrir
        o menu — usado como exclusão no fallback amplo (Abordagem C), pra não confundir
        widgets sempre-montados (ex: lista de países do telefone) com as opções reais
        do dropdown que acabou de abrir."""
        try:
            loc = self.page.locator(self._OPTION_SELECTOR)
            texts = await loc.all_inner_texts()
            return [re.sub(r"\s+", " ", t).strip() for t in texts if t and t.strip()]
        except Exception:
            return []

    async def _field_id(self, element: Any) -> str | None:
        try:
            field_id = await element.get_attribute("id")
            return field_id or None
        except Exception:
            return None

    async def _scoped_locator(self, element: Any) -> Any | None:
        """Locator escopado pelo instanceId do react-select (Abordagem A) — o Greenhouse
        usa o próprio id do campo como prefixo das opções (ex: id do campo
        'question_67357342' -> opções com id 'react-select-question_67357342-option-N').
        None se o campo não tem id ou se não há match com esse prefixo (cai pro
        fallback amplo em _visible_options/_click_option_exact)."""
        field_id = await self._field_id(element)
        if not field_id:
            return None
        loc = self.page.locator(f'[id^="react-select-{field_id}-option"]')
        try:
            if await loc.count() > 0:
                return loc
        except Exception:
            pass
        return None

    async def _open_menu(self, element: Any) -> None:
        with contextlib.suppress(Exception):
            await element.scroll_into_view_if_needed()
        try:
            await element.click()
        except Exception:
            with contextlib.suppress(Exception):
                await element.evaluate("el => el.focus()")  # clique interceptado por overlay
        await asyncio.sleep(0.4)

    async def _type_and_reload(self, element: Any, answer: str) -> list[str]:
        """Select async/typeahead (ex: cidade): digitar carrega as opções."""
        try:
            await element.type(answer, delay=30)
            await asyncio.sleep(0.7)
        except Exception:
            pass
        return await self._visible_options()

    async def _choose_and_click(
        self, element: Any, label_text: str, answer: str, options: list[str]
    ) -> bool:
        """Escolhe a opção (match local; senão LLM entre as opções reais), clica a
        EXATA e verifica a seleção. Sem escolha confirmada → False."""
        from gauntler.application.answers.option_matcher import match_option_locally

        choice = match_option_locally(answer, options) or await self._llm_pick(
            label_text, answer, options
        )
        if choice and await self._click_option_exact(choice):
            await asyncio.sleep(0.2)
            if await self._selected_value(element):
                return True
        return False

    async def _visible_options(self) -> list[str]:
        """Textos das opções do dropdown aberto. Usa locator com auto-wait (as opções
        do react-select renderizam com delay) — um querySelectorAll único pegaria a
        lista ainda vazia."""
        try:
            loc = self.page.locator(self._OPTION_SELECTOR)
            try:
                await loc.first.wait_for(state="visible", timeout=2000)
            except Exception:
                return []
            texts = await loc.all_inner_texts()
            return [re.sub(r"\s+", " ", t).strip() for t in texts if t and t.strip()][:300]
        except Exception:
            return []

    async def _click_option_exact(self, text: str) -> bool:
        """Clica na opção cujo texto normalizado é EXATAMENTE `text` (via locator)."""
        try:
            want = re.sub(r"\s+", " ", text or "").strip().lower()
            loc = self.page.locator(self._OPTION_SELECTOR)
            for i in range(await loc.count()):
                option = loc.nth(i)
                if re.sub(r"\s+", " ", await option.inner_text()).strip().lower() == want:
                    await option.click()
                    return True
            return False
        except Exception:
            return False

    async def _llm_pick(self, label_text: str, answer: str, options: list[str]) -> str | None:
        """Desambigua via LLM entre as opções reais. Sem opções ou erro → None."""
        if not options:
            return None
        try:
            from gauntler.application.answers.option_matcher import pick_option_with_llm
            from gauntler.core.llm import make_caller

            caller = make_caller(self.config)
            model = (
                self.config.get("eval_model")
                or self.config.get("llm_model")
                or "claude-haiku-4-5-20251001"
            )
            return await pick_option_with_llm(
                label_text, answer, options, self.profile, caller, model
            )
        except Exception:
            return None

    async def _selected_value(self, element: Any) -> str:
        """Lê o valor exibido pelo react-select (.select__single-value) subindo a árvore."""
        try:
            value: str = await element.evaluate(
                """el => {
                    let c = el;
                    for (let i = 0; i < 6 && c; i++) {
                        if (c.querySelector && c.querySelector('.select__single-value')) break;
                        c = c.parentElement;
                    }
                    const sv = c && c.querySelector ? c.querySelector('.select__single-value') : null;
                    return sv ? sv.innerText.trim() : '';
                }"""
            )
            return value
        except Exception:
            return ""

    async def _upload_cv(self, cv_path: str) -> str:
        """Anexa o CV. Devolve "filled", "skipped" ou "failed:<motivo>". Tenta locator
        (resiliente a inputs ocultos) e depois query_selector."""
        if not cv_path:
            return "skipped"
        try:
            file_locator = self.page.locator("input[type='file']").first
            if await file_locator.count() > 0:
                await file_locator.set_input_files(cv_path)
                await asyncio.sleep(1)
                logger.info("_upload_cv: CV anexado via locator")
                return "filled"

            file_input = await self.page.query_selector("input[type='file']")
            if file_input:
                await file_input.set_input_files(cv_path)
                await asyncio.sleep(1)
                logger.info("_upload_cv: CV anexado via query_selector")
                return "filled"

            logger.warning("_upload_cv: nenhum input[type='file'] encontrado")
            return "failed:no_file_input"
        except Exception as e:
            logger.warning("_upload_cv: exception — %s", e)
            return f"failed:{type(e).__name__}"

    async def submit(self) -> str:
        empty = await self._empty_required_fields()
        if empty:
            logger.warning("submit: %d campo(s) obrigatório(s) vazios: %s", len(empty), empty)
        return await self._click_submit_and_classify()

    async def _empty_required_fields(self) -> list[str]:
        """Labels com '*' cujo input/select está visivelmente vazio antes do submit."""
        logger.info("submit: verificando campos obrigatórios")
        empty: list[str] = await self.page.evaluate("""() => {
            const empty = [];
            for (const label of document.querySelectorAll('label')) {
                if (!label.textContent.includes('*')) continue;
                const forId = label.getAttribute('for');
                if (!forId) continue;
                const el = document.getElementById(forId);
                if (!el) continue;
                const tag = el.tagName.toLowerCase();
                if ((tag === 'input' || tag === 'textarea') && !el.value.trim()) {
                    empty.push(label.innerText.trim());
                } else if (tag === 'select' && !el.value) {
                    empty.push(label.innerText.trim());
                }
            }
            return empty;
        }""")
        return empty

    async def _click_submit_and_classify(self) -> str:
        logger.info("submit: click")
        try:
            submit_btn = await self.page.query_selector(
                "input[type='submit'], button[type='submit']"
            )
            if not submit_btn:
                logger.warning("submit: botão não encontrado")
                return "failed"
            await submit_btn.click()
            await self.page.wait_for_load_state("networkidle", timeout=15000)

            from gauntler.application.appliers.base import classify_submit_outcome

            outcome = await classify_submit_outcome(self.page)
            if outcome.startswith("failed:validation_errors"):
                logger.warning("submit: form ainda visível após submit — %s", outcome)
            else:
                logger.info("submit: outcome=%s", outcome)
            return outcome
        except Exception as e:
            logger.warning("submit: exception — %s", e)
            return "failed"
