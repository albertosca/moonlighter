import asyncio
import contextlib
import re
from typing import Any

from gauntler.application.appliers.base import (
    BaseApplier,
    classify_submit_outcome,
    fill_field,
    is_skip,
    query_labels_with_fallback,
)
from gauntler.core.llm import make_caller
from gauntler.core.log import get_logger
from playwright.async_api import TimeoutError as PlaywrightTimeout

logger = get_logger(__name__)

# Labels of the CV/resume upload area — the attachment is handled by _upload_cv, so
# these must not go to the LLM as text fields (or they'd get a garbage answer).
_UPLOAD_LABELS = {
    "resume/cv",
    "cover letter",
    "attach",
    "anexar",
    "enter manually",
    "informe manualmente",
}


def _log_fill_stats(status: dict[str, str]) -> None:
    filled = sum(1 for s in status.values() if s == "filled")
    failed = [label for label, s in status.items() if s.startswith("failed")]
    skipped = sum(1 for s in status.values() if s == "skipped")
    logger.info("fill_form: %d filled, %d failed, %d skipped", filled, len(failed), skipped)
    if failed:
        logger.warning("fill_form: fields with failures: %s", failed)


class GreenhouseApplier(BaseApplier):
    _OPTION_SELECTOR = '.select__option, [role="option"], [role="listbox"] li'

    async def detect(self) -> bool:
        match = "greenhouse.io" in self.page.url or "boards.greenhouse.io" in self.page.url
        if match:
            logger.debug("detect: greenhouse ✓ (%s)", self.page.url)
        return match

    async def extract_fields(self) -> list[str]:
        await self._open_application()
        label_els = await query_labels_with_fallback(
            self.page,
            ["label, .field-label", ".application-question label", "[data-field-label]"],
        )
        labels = []
        for el in label_els:
            text = (await el.inner_text()).strip()
            if text and text.lower() not in _UPLOAD_LABELS:
                labels.append(text)
        logger.debug("extract_fields: %d fields", len(labels))
        return labels

    async def _open_application(self) -> None:
        """Clicks the 'Apply' button when the form is not yet open."""
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
        """Fills the form. Returns {label: "filled"|"skipped"|"failed:<reason>"}.
        Never raises — failures go into the return value and the log."""
        logger.info("fill_form: start (%d answers)", len(answers))
        status = {label: await self._fill_one(label, answer) for label, answer in answers.items()}
        if cv_path:
            status["__cv__"] = await self._upload_cv(cv_path)
        _log_fill_stats(status)
        return status

    async def _fill_one(self, label_text: str, answer: str) -> str:
        if is_skip(answer):
            return "skipped"
        try:
            field = await self._find_field(label_text)
            if field is None:
                logger.debug("fill_form: field not found — '%s'", label_text)
                return "failed:not_found"

            if await self._is_custom_combobox(field):
                ok = await self._select_custom_option(field, label_text, answer)
                return "filled" if ok else "failed:custom_dropdown"

            tag = await field.evaluate("el => el.tagName.toLowerCase()")
            if tag in ("input", "textarea", "select"):
                await fill_field(field, answer)
                await asyncio.sleep(0.2)
                return "filled"

            ok = await self._fill_custom_element(field, label_text, answer)
            return "filled" if ok else "failed:custom_element_unsupported"
        except Exception as e:
            logger.debug("fill_form: exception in '%s': %s", label_text, e)
            return f"failed:{type(e).__name__}"

    async def _is_custom_combobox(self, field: Any) -> bool:
        """A react-select exposes an <input role=combobox aria-haspopup class=select__input>.
        Treating it as a text input only TYPES into the search box without selecting the
        option — and would still report 'filled' (false positive). That's why we route to
        the custom dropdown handler instead of the native fill_field."""
        return bool(
            await field.evaluate(
                "el => el.getAttribute('role') === 'combobox'"
                " || el.getAttribute('aria-haspopup') === 'true'"
                " || (el.className || '').toLowerCase().includes('select__input')"
            )
        )

    async def _find_field(self, label_text: str) -> Any:
        """Locates the input associated with a label, in cascade. Returns the
        ElementHandle or None."""
        # 1) get_by_label (resolves for/aria-label/labelledby + normalizes text)
        for exact in (True, False):
            locator = self.page.get_by_label(label_text, exact=exact)
            if await locator.count() > 0:
                return await locator.first.element_handle()

        # 2) JS: normalizes the label (strip *, &nbsp;, spaces) and grabs the `for` attribute
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

        # 3) direct aria-label
        escaped = label_text.replace("'", "\\'")
        return await self.page.query_selector(f"[aria-label='{escaped}']")

    async def _fill_custom_element(self, element: Any, label_text: str, answer: str) -> bool:
        """Handles non-native elements: custom dropdowns (role=combobox/listbox) and
        typeaheads (autocomplete). True if it managed to fill it in."""
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
        """Types into the field and clicks the first suggestion that contains the answer."""
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
                "_fill_custom_element typeahead: '%s' did not find '%s'. Visible options: %s",
                label_text,
                answer,
                result.get("options") or "(none)",
            )
            return False
        except Exception as e:
            logger.warning("_fill_custom_element typeahead: '%s' exception — %s", label_text, e)
            return False

    async def _select_custom_option(self, element: Any, label_text: str, answer: str) -> bool:
        """Selects an option in a react-select ALWAYS choosing by the option's REAL TEXT
        (local match or LLM) and clicking the exact option, verifying via
        .select__single-value. NEVER presses Enter blindly — in the filtered list Enter
        would grab the highlighted option, which could be the wrong one (typing 'Fluent'
        filters to 'not able to speak fluently' and Enter would grab the negative one).
        Static selects are chosen from the full list without typing; typing only happens
        when there are no static options (async/typeahead select that loads on typing)."""
        try:
            before_texts = await self._option_texts_snapshot()
            await self._open_menu(element)
            options = await self._visible_options(
                element, before_texts
            ) or await self._type_and_reload(element, answer, before_texts)
            if options and await self._choose_and_click(
                element, label_text, answer, options, before_texts
            ):
                return True

            logger.warning(
                "_select_custom_option: '%s' did not select '%s'. Options: %s",
                label_text,
                answer,
                options or "(none — dropdown did not open/load?)",
            )
            with contextlib.suppress(Exception):
                await self.page.keyboard.press("Escape")
            return False
        except Exception as e:
            logger.warning("_select_custom_option: '%s' exception — %s", label_text, e)
            return False

    async def _option_texts_snapshot(self) -> list[str]:
        """Texts of ALL options that already match _OPTION_SELECTOR BEFORE opening the
        menu — used as an exclusion set in the broad fallback (Approach C), to avoid
        confusing always-mounted widgets (e.g. the phone country list) with the real
        options of the dropdown that just opened."""
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
        """Locator scoped by the react-select instanceId (Approach A) — Greenhouse
        uses the field's own id as the options' prefix (e.g. field id
        'question_67357342' -> options with id 'react-select-question_67357342-option-N').
        None if the field has no id or there's no match with that prefix (falls back
        to the broad fallback in _visible_options/_click_option_exact)."""
        field_id = await self._field_id(element)
        if not field_id:
            return None
        try:
            loc = self.page.locator(f'[id^="react-select-{field_id}-option"]')
            if await loc.count() > 0:
                return loc
        except Exception as e:
            logger.debug("scoped locator lookup failed for %r: %s", field_id, e)
        return None

    async def _open_menu(self, element: Any) -> None:
        with contextlib.suppress(Exception):
            await element.scroll_into_view_if_needed()
        try:
            await element.click()
        except Exception:
            with contextlib.suppress(Exception):
                await element.evaluate("el => el.focus()")  # click intercepted by overlay
        await asyncio.sleep(0.4)

    async def _type_and_reload(
        self, element: Any, answer: str, before_texts: list[str] | None = None
    ) -> list[str]:
        """Async/typeahead select (e.g. city): typing loads the options."""
        try:
            await element.type(answer, delay=30)
            await asyncio.sleep(0.7)
        except Exception as e:
            logger.debug("typeahead typing failed: %s", e)
        return await self._visible_options(element, before_texts)

    async def _choose_and_click(
        self,
        element: Any,
        label_text: str,
        answer: str,
        options: list[str],
        before_texts: list[str] | None = None,
    ) -> bool:
        """Chooses the option (local match; otherwise LLM among the real options),
        clicks the EXACT one, and verifies the selection. No confirmed choice → False."""
        from gauntler.application.answers.option_matcher import match_option_locally

        choice = match_option_locally(answer, options) or await self._llm_pick(
            label_text, answer, options
        )
        if choice and await self._click_option_exact(choice, element, before_texts or []):
            await asyncio.sleep(0.2)
            if await self._selected_value(element):
                return True
        return False

    async def _visible_options(
        self, element: Any, before_texts: list[str] | None = None
    ) -> list[str]:
        """Texts of the open dropdown's options. Approach A: locator scoped by the
        field's id (react-select instanceId) — used directly, with no risk of
        pollution. Without that, falls back to the broad selector with auto-wait
        (react-select options render with a delay) and excludes any text already
        present in `before_texts` (Approach C — always-mounted widgets, e.g. the
        phone country list, don't count)."""
        try:
            scoped = await self._scoped_locator(element)
            if scoped is not None:
                texts = await scoped.all_inner_texts()
                return [re.sub(r"\s+", " ", t).strip() for t in texts if t and t.strip()][:300]

            loc = self.page.locator(self._OPTION_SELECTOR)
            try:
                await loc.first.wait_for(state="visible", timeout=2000)
            except Exception:
                return []
            texts = await loc.all_inner_texts()
            cleaned = [re.sub(r"\s+", " ", t).strip() for t in texts if t and t.strip()]
            exclude = set(before_texts or [])
            return [t for t in cleaned if t not in exclude][:300]
        except Exception:
            return []

    async def _click_option_exact(
        self, text: str, element: Any, before_texts: list[str] | None = None
    ) -> bool:
        """Clicks the option whose normalized text is EXACTLY `text`. Approach A:
        inside the locator scoped by the field's id. Without that, falls back to
        the broad selector (Approach C), ignoring texts already present in
        `before_texts`."""
        try:
            want = re.sub(r"\s+", " ", text or "").strip().lower()
            scoped = await self._scoped_locator(element)
            loc = scoped if scoped is not None else self.page.locator(self._OPTION_SELECTOR)
            exclude = (
                set()
                if scoped is not None
                else {re.sub(r"\s+", " ", t).strip().lower() for t in (before_texts or [])}
            )
            for i in range(await loc.count()):
                option = loc.nth(i)
                t = re.sub(r"\s+", " ", await option.inner_text()).strip().lower()
                if t == want and t not in exclude:
                    await option.click()
                    return True
            return False
        except Exception:
            return False

    async def _llm_pick(self, label_text: str, answer: str, options: list[str]) -> str | None:
        """Disambiguates via LLM among the real options. No options or an error → None."""
        if not options:
            return None
        try:
            from gauntler.application.answers.option_matcher import pick_option_with_llm

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
        """Reads the value displayed by react-select (.select__single-value), walking up the tree."""
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
        """Attaches the CV. Returns "filled", "skipped" or "failed:<reason>". Tries
        locator (resilient to hidden inputs) and then query_selector."""
        if not cv_path:
            return "skipped"
        try:
            file_locator = self.page.locator("input[type='file']").first
            if await file_locator.count() > 0:
                await file_locator.set_input_files(cv_path)
                await asyncio.sleep(1)
                logger.info("_upload_cv: CV attached via locator")
                return "filled"

            file_input = await self.page.query_selector("input[type='file']")
            if file_input:
                await file_input.set_input_files(cv_path)
                await asyncio.sleep(1)
                logger.info("_upload_cv: CV attached via query_selector")
                return "filled"

            logger.warning("_upload_cv: no input[type='file'] found")
            return "failed:no_file_input"
        except Exception as e:
            logger.warning("_upload_cv: exception — %s", e)
            return f"failed:{type(e).__name__}"

    async def submit(self) -> str:
        empty = await self._empty_required_fields()
        if empty:
            logger.warning("submit: %d required field(s) empty: %s", len(empty), empty)
        return await self._click_submit_and_classify()

    async def _empty_required_fields(self) -> list[str]:
        """Labels with '*' whose input/select is visibly empty before submit."""
        logger.info("submit: checking required fields")
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
                logger.warning("submit: button not found")
                return "failed"
            await submit_btn.click()
            await self.page.wait_for_load_state("networkidle", timeout=15000)

            outcome = await classify_submit_outcome(self.page)
            if outcome.startswith("failed:validation_errors"):
                logger.warning("submit: form still visible after submit — %s", outcome)
            else:
                logger.info("submit: outcome=%s", outcome)
            return outcome
        except Exception as e:
            logger.warning("submit: exception — %s", e)
            return "failed"
