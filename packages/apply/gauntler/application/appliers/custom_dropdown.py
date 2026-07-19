"""
Fills Greenhouse's non-native form elements: react-select comboboxes and
typeahead/autocomplete fields that the native fill_field path (input/textarea/
select) can't handle. Extracted from greenhouse.py because this machinery is
self-contained (page + config + profile is all it needs) and carries most of
the applier's complexity — the option-matching fallback order (local match ->
LLM pick -> typeahead-only-when-there-are-no-static-options) is exactly the
part validated against a real Nubank Greenhouse form; it must stay
byte-identical to the code that was live-tested.
"""

import asyncio
import contextlib
import re
from typing import Any

from gauntler.core.llm import make_caller
from gauntler.core.log import get_logger
from playwright.async_api import Page

logger = get_logger(__name__)


class CustomDropdownFiller:
    """Handles react-select comboboxes and typeahead/autocomplete fields on
    behalf of a GreenhouseApplier. Public entry points: is_custom_combobox,
    select_custom_option, fill_custom_element."""

    _OPTION_SELECTOR = '.select__option, [role="option"], [role="listbox"] li'

    def __init__(self, page: Page, config: dict[str, Any], profile: dict[str, Any]):
        self.page = page
        self.config = config
        self.profile = profile

    async def is_custom_combobox(self, field: Any) -> bool:
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

    async def fill_custom_element(self, element: Any, label_text: str, answer: str) -> bool:
        """Handles non-native elements: custom dropdowns (role=combobox/listbox) and
        typeaheads (autocomplete). True if it managed to fill it in."""
        if await self._looks_like_dropdown(element):
            return await self.select_custom_option(element, label_text, answer)
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
                "fill_custom_element typeahead: '%s' did not find '%s'. Visible options: %s",
                label_text,
                answer,
                result.get("options") or "(none)",
            )
            return False
        except Exception as e:
            logger.warning("fill_custom_element typeahead: '%s' exception — %s", label_text, e)
            return False

    async def select_custom_option(self, element: Any, label_text: str, answer: str) -> bool:
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
                "select_custom_option: '%s' did not select '%s'. Options: %s",
                label_text,
                answer,
                options or "(none — dropdown did not open/load?)",
            )
            with contextlib.suppress(Exception):
                await self.page.keyboard.press("Escape")
            return False
        except Exception as e:
            logger.warning("select_custom_option: '%s' exception — %s", label_text, e)
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
