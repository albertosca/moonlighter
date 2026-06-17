import asyncio
import re

from playwright.async_api import TimeoutError as PlaywrightTimeout

from candidatador.applicator.base import BaseApplier
from candidatador.log import get_logger

logger = get_logger(__name__)


class GreenhouseApplier(BaseApplier):
    async def detect(self) -> bool:
        match = "greenhouse.io" in self.page.url or "boards.greenhouse.io" in self.page.url
        if match:
            logger.debug("detect: greenhouse ✓ (%s)", self.page.url)
        return match

    async def extract_fields(self) -> list[str]:
        try:
            apply_btn = await self.page.query_selector(
                "a#apply, button#apply, a[data-greenhouse-job-board-apply]"
            )
            if apply_btn:
                await apply_btn.click()
                await self.page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            pass

        from candidatador.applicator.base import _query_labels_with_fallback

        label_els = await _query_labels_with_fallback(
            self.page,
            [
                "label, .field-label",
                ".application-question label",
                "[data-field-label]",
            ],
        )
        # Campos da área de upload de CV/currículo — o anexo é tratado por _upload_cv,
        # então não devem ir pro LLM como campos de texto (senão recebem resposta-lixo).
        _UPLOAD_LABELS = {
            "resume/cv",
            "cover letter",
            "attach",
            "anexar",
            "enter manually",
            "informe manualmente",
        }
        labels = []
        for el in label_els:
            text = (await el.inner_text()).strip()
            if text and text.lower() not in _UPLOAD_LABELS:
                labels.append(text)
        logger.debug("extract_fields: %d campos", len(labels))
        return labels

    async def fill_form(self, answers: dict[str, str], cv_path: str) -> dict[str, str]:
        """
        Preenche o formulário com as respostas fornecidas.
        Retorna um dict {label: status} onde status é "filled", "skipped" ou "failed:<motivo>".
        Nunca levanta exceção — falhas são registradas no retorno e no log.
        """
        from candidatador.applicator.base import _fill_field

        status: dict[str, str] = {}
        logger.info("fill_form: start (%d respostas)", len(answers))

        for label_text, answer in answers.items():
            if not answer or answer in (
                "__SKIP__",
                "__MANUAL_UPLOAD_REQUIRED__",
                "__NEEDS_REVIEW__",
            ):
                status[label_text] = "skipped"
                continue
            try:
                field = await self._find_field(label_text)
                if field is None:
                    logger.debug("fill_form: campo não encontrado — '%s'", label_text)
                    status[label_text] = "failed:not_found"
                    continue

                tag = await field.evaluate("el => el.tagName.toLowerCase()")

                # react-select e afins expõem um <input role=combobox aria-haspopup>
                # (class select__input). Tratar como text input só DIGITA no campo de
                # busca sem selecionar a opção — e ainda reportaria 'filled' (falso
                # positivo). Roteamos esses para o handler de dropdown custom.
                is_custom_combobox = await field.evaluate(
                    "el => el.getAttribute('role') === 'combobox'"
                    " || el.getAttribute('aria-haspopup') === 'true'"
                    " || (el.className || '').toLowerCase().includes('select__input')"
                )

                if is_custom_combobox:
                    # fill_form já sabe que é combobox — vai direto pro handler de
                    # react-select (digita/filtra/verifica), sem re-detectar o tipo.
                    filled = await self._select_custom_option(field, label_text, answer)
                    status[label_text] = "filled" if filled else "failed:custom_dropdown"
                elif tag in ("input", "textarea", "select"):
                    await _fill_field(field, answer)
                    await asyncio.sleep(0.2)
                    status[label_text] = "filled"
                else:
                    # Elemento não é um input nativo — pode ser custom dropdown ou typeahead
                    filled = await self._fill_custom_element(field, label_text, answer)
                    status[label_text] = "filled" if filled else "failed:custom_element_unsupported"

            except Exception as e:
                logger.debug("fill_form: exception em '%s': %s", label_text, e)
                status[label_text] = f"failed:{type(e).__name__}"

        # Upload de CV
        cv_status = await self._upload_cv(cv_path)
        if cv_path:
            status["__cv__"] = cv_status

        filled = sum(1 for s in status.values() if s == "filled")
        failed = [k for k, s in status.items() if s.startswith("failed")]
        logger.info(
            "fill_form: %d filled, %d failed, %d skipped",
            filled,
            sum(1 for s in status.values() if s.startswith("failed")),
            sum(1 for s in status.values() if s == "skipped"),
        )
        if failed:
            logger.warning("fill_form: campos com falha: %s", failed)

        return status

    async def _find_field(self, label_text: str):
        """
        Estratégia em cascata para localizar o elemento de input associado a um label.
        Retorna o ElementHandle ou None.
        """
        # Estratégia 1: get_by_label (resolve for/aria-label/labelledby + normaliza texto)
        for exact in (True, False):
            locator = self.page.get_by_label(label_text, exact=exact)
            if await locator.count() > 0:
                return await locator.first.element_handle()

        # Estratégia 2: JS — normaliza label (strip *, &nbsp;, espaços) → pega o `for` attribute
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

        # Estratégia 3: aria-label direto
        escaped = label_text.replace("'", "\\'")
        el = await self.page.query_selector(f"[aria-label='{escaped}']")
        if el:
            return el

        return None

    async def _fill_custom_element(self, element, label_text: str, answer: str) -> bool:
        """
        Trata elementos não-nativos: custom dropdowns (role=combobox/listbox)
        e typeaheads (autocomplete). Retorna True se conseguiu preencher.
        """
        role = await element.evaluate(
            "el => el.getAttribute('role') || el.getAttribute('aria-haspopup') || ''"
        )

        # Custom dropdown / combobox
        if role in ("combobox", "listbox", "button") or await element.evaluate(
            "el => el.classList.toString().toLowerCase().includes('select') || el.classList.toString().toLowerCase().includes('dropdown')"
        ):
            return await self._select_custom_option(element, label_text, answer)

        # Tenta typeahead: digita e espera sugestões
        try:
            await element.click()
            await element.type(answer, delay=50)
            await asyncio.sleep(0.6)
            # Coleta sugestões visíveis e tenta clicar na que bate
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
            options = result.get("options", [])
            logger.warning(
                "_fill_custom_element typeahead: '%s' não achou '%s'. Opções visíveis: %s",
                label_text,
                answer,
                options or "(nenhuma)",
            )
            return False
        except Exception as e:
            logger.warning("_fill_custom_element typeahead: '%s' exception — %s", label_text, e)
            return False

    async def _select_custom_option(self, element, label_text: str, answer: str) -> bool:
        """
        Seleciona uma opção num react-select / dropdown custom escolhendo SEMPRE pelo
        TEXTO REAL da opção (match local ou LLM) e clicando a opção exata, com
        verificação via .select__single-value. NUNCA dá Enter cego (Enter na lista
        filtrada selecionaria a opção destacada — pode ser a errada, ex: digitar
        'Fluent' filtra para 'not able to speak fluently' e o Enter pegaria a negativa).
        Em selects ESTÁTICOS escolhe pela lista completa SEM digitar; só digita quando
        não há opções estáticas (select async/typeahead que carrega ao digitar).
        """
        try:
            try:
                await element.scroll_into_view_if_needed()
            except Exception:
                pass
            # Abre o menu. Em caso de clique interceptado por overlay, foca via JS.
            try:
                await element.click()
            except Exception:
                try:
                    await element.evaluate("el => el.focus()")
                except Exception:
                    pass
            await asyncio.sleep(0.4)

            static_opts = await self._visible_options()
            if static_opts:
                # Select estático/descritivo: escolher pela LISTA COMPLETA, sem digitar.
                if await self._choose_and_click(element, label_text, answer, static_opts):
                    return True
                shown = static_opts
            else:
                # Sem opções estáticas → async/typeahead (ex: cidade): digitar carrega.
                try:
                    await element.type(answer, delay=30)
                    await asyncio.sleep(0.7)
                except Exception:
                    pass
                loaded_opts = await self._visible_options()
                if loaded_opts and await self._choose_and_click(
                    element, label_text, answer, loaded_opts
                ):
                    return True
                shown = loaded_opts

            logger.warning(
                "_select_custom_option: '%s' não selecionou '%s'. Opções: %s",
                label_text,
                answer,
                shown or "(nenhuma — dropdown não abriu/carregou?)",
            )
            try:
                await self.page.keyboard.press("Escape")
            except Exception:
                pass
            return False
        except Exception as e:
            logger.warning("_select_custom_option: '%s' exception — %s", label_text, e)
            return False

    async def _choose_and_click(
        self, element, label_text: str, answer: str, options: list[str]
    ) -> bool:
        """Escolhe a opção (match local; senão LLM entre as opções reais), clica a
        EXATA e verifica a seleção. Sem escolha confirmada → False."""
        from candidatador.applicator.option_matcher import match_option_locally

        choice = match_option_locally(answer, options)
        if not choice:
            choice = await self._llm_pick(label_text, answer, options)
        if choice and await self._click_option_exact(choice):
            await asyncio.sleep(0.2)
            if await self._selected_value(element):
                return True
        return False

    _OPTION_SELECTOR = '.select__option, [role="option"], [role="listbox"] li'

    async def _visible_options(self) -> list[str]:
        """Lista os textos das opções do dropdown aberto. Usa locator com auto-wait
        (as opções do react-select renderizam com delay) — um querySelectorAll único
        pegaria a lista ainda vazia."""
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
            n = await loc.count()
            for i in range(n):
                t = re.sub(r"\s+", " ", await loc.nth(i).inner_text()).strip().lower()
                if t == want:
                    await loc.nth(i).click()
                    return True
            return False
        except Exception:
            return False

    async def _llm_pick(self, label_text: str, answer: str, options: list[str]) -> str | None:
        """Desambigua via LLM entre as opções reais. Sem opções ou erro → None."""
        if not options:
            return None
        try:
            from candidatador.applicator.option_matcher import pick_option_with_llm
            from candidatador.llm import make_caller

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

    async def _selected_value(self, element) -> str:
        """Lê o valor exibido pelo react-select (.select__single-value) subindo a árvore."""
        try:
            return await element.evaluate(
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
        except Exception:
            return ""

    async def _upload_cv(self, cv_path: str) -> str:
        """
        Faz upload do CV. Retorna "filled", "skipped" ou "failed:<motivo>".
        Tenta múltiplas estratégias para encontrar o input de arquivo.
        """
        if not cv_path:
            return "skipped"
        try:
            # Estratégia 1: locator (mais resiliente — funciona com inputs ocultos)
            file_locator = self.page.locator("input[type='file']").first
            if await file_locator.count() > 0:
                await file_locator.set_input_files(cv_path)
                await asyncio.sleep(1)
                logger.info("_upload_cv: CV anexado via locator")
                return "filled"

            # Estratégia 2: query_selector com force (para inputs hidden)
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
        logger.info("submit: verificando campos obrigatórios")

        # Verifica se há campos obrigatórios visivelmente vazios antes de submeter
        empty_required = await self.page.evaluate("""() => {
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
        if empty_required:
            logger.warning(
                "submit: %d campo(s) obrigatório(s) vazios: %s", len(empty_required), empty_required
            )

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

            from candidatador.applicator.base import classify_submit_outcome

            outcome = await classify_submit_outcome(self.page)
            if outcome.startswith("failed:validation_errors"):
                logger.warning("submit: form ainda visível após submit — %s", outcome)
            else:
                logger.info("submit: outcome=%s", outcome)
            return outcome
        except Exception as e:
            logger.warning("submit: exception — %s", e)
            return "failed"
