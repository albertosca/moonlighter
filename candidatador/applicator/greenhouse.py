import asyncio
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
            apply_btn = await self.page.query_selector("a#apply, button#apply, a[data-greenhouse-job-board-apply]")
            if apply_btn:
                await apply_btn.click()
                await self.page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            pass

        from candidatador.applicator.base import _query_labels_with_fallback
        label_els = await _query_labels_with_fallback(self.page, [
            "label, .field-label",
            ".application-question label",
            "[data-field-label]",
        ])
        labels = []
        for el in label_els:
            text = (await el.inner_text()).strip()
            if text and text not in ("Resume/CV", "Cover Letter"):
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
            if not answer or answer in ("__SKIP__", "__MANUAL_UPLOAD_REQUIRED__"):
                status[label_text] = "skipped"
                continue
            try:
                field = await self._find_field(label_text)
                if field is None:
                    logger.debug("fill_form: campo não encontrado — '%s'", label_text)
                    status[label_text] = "failed:not_found"
                    continue

                tag = await field.evaluate("el => el.tagName.toLowerCase()")

                if tag in ("input", "textarea", "select"):
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
        logger.info("fill_form: %d filled, %d failed, %d skipped",
                    filled,
                    sum(1 for s in status.values() if s.startswith("failed")),
                    sum(1 for s in status.values() if s == "skipped"))
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
        role = await element.evaluate("el => el.getAttribute('role') || el.getAttribute('aria-haspopup') || ''")

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
                label_text, answer, options or "(nenhuma)"
            )
            return False
        except Exception as e:
            logger.warning("_fill_custom_element typeahead: '%s' exception — %s", label_text, e)
            return False

    async def _select_custom_option(self, element, label_text: str, answer: str) -> bool:
        """Clica no custom dropdown e seleciona a opção pelo texto."""
        try:
            await element.click()
            await asyncio.sleep(0.4)
            # Coleta todas as opções visíveis e tenta clicar na que bate
            result = await self.page.evaluate(
                """(answer) => {
                    const a = answer.toLowerCase().trim();
                    const selectors = [
                        '[role="option"]', '[role="listbox"] li',
                        '.select__option', '.dropdown__item',
                        'ul[role="listbox"] li', '[data-testid*="option"]',
                    ];
                    const visible = [];
                    for (const sel of selectors) {
                        for (const el of document.querySelectorAll(sel)) {
                            const t = el.innerText.trim();
                            if (t) visible.push(t);
                            const tl = t.toLowerCase();
                            if (tl === a || tl.startsWith(a) || a.startsWith(tl)) {
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
                "_select_custom_option: '%s' não achou '%s'. Opções disponíveis: %s",
                label_text, answer, options or "(nenhuma — dropdown não abriu?)"
            )
            await self.page.keyboard.press("Escape")
            return False
        except Exception as e:
            logger.warning("_select_custom_option: '%s' exception — %s", label_text, e)
            return False

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
        from candidatador.applicator.base import _confirm_submitted
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
            logger.warning("submit: %d campo(s) obrigatório(s) vazios: %s", len(empty_required), empty_required)

        logger.info("submit: click")
        try:
            submit_btn = await self.page.query_selector("input[type='submit'], button[type='submit']")
            if not submit_btn:
                logger.warning("submit: botão não encontrado")
                return "failed"
            await submit_btn.click()
            await self.page.wait_for_load_state("networkidle", timeout=15000)

            # Detecta sucesso pela URL/texto de confirmação
            if await _confirm_submitted(self.page):
                logger.info("submit: outcome=submitted")
                return "submitted"

            # Detecta se o form ainda está visível (= validação falhou)
            form_still_visible = await self.page.evaluate(
                "() => !!document.querySelector('form input[type=\"submit\"], form button[type=\"submit\"]')"
            )
            if form_still_visible:
                # Coleta mensagens de erro visíveis
                error_messages = await self.page.evaluate("""() => {
                    const msgs = [];
                    for (const el of document.querySelectorAll(
                        '[aria-invalid="true"], .error, .field-error, [data-error], .invalid-feedback'
                    )) {
                        if (el.innerText.trim()) msgs.push(el.innerText.trim());
                    }
                    return msgs.slice(0, 10);
                }""")
                logger.warning("submit: form ainda visível após submit — erros de validação: %s", error_messages)
                return f"failed:validation_errors:{error_messages}"

            logger.info("submit: outcome=unverified")
            return "unverified"
        except Exception as e:
            logger.warning("submit: exception — %s", e)
            return "failed"
