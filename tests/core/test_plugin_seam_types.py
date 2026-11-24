"""The functions moonlighter-linkedin calls with a plain dict keep accepting one.

mypy checks this file through the tests ratchet: narrowing any of them to Config makes
the assignments below type errors. The plugin pins feat/ats-automation, so its own CI
would only see such a break after that branch is next rebased onto main.
"""

from collections.abc import Callable
from typing import Any

from moonlighter.core import browser
from moonlighter.core.config.paths import browser_executable


def test_the_plugin_seam_takes_a_plain_dict():
    plugin_config: dict[str, Any] = {"browser_path": "/usr/bin/chromium"}
    assert browser_executable(plugin_config) == "/usr/bin/chromium"
    # Coroutines that launch a browser: assigned, never awaited, so mypy compares the
    # parameter types without the test starting Chromium.
    seam: list[Callable[[dict[str, Any]], object]] = [browser.new_page, browser.get_context]
    assert all(callable(function) for function in seam)
