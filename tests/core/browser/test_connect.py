"""get_context connects over CDP, launching the browser only when no port of ours answers, and new_page opens its page in that context."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moonlighter.core import browser
from tests.core.browser_config import CONFIG


def _make_cdp_mocks():
    """Build mocks for the CDP connection path."""
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=MagicMock())

    mock_browser = MagicMock()
    mock_browser.is_connected = MagicMock(return_value=True)
    mock_browser.contexts = [mock_context]
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_chromium = MagicMock()
    mock_chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

    mock_playwright = MagicMock()
    mock_playwright.chromium = mock_chromium
    mock_playwright.stop = AsyncMock()

    mock_pw_instance = MagicMock()
    mock_pw_instance.start = AsyncMock(return_value=mock_playwright)

    mock_process = MagicMock()
    mock_process.terminate = MagicMock()
    mock_process.kill = MagicMock()

    return mock_pw_instance, mock_playwright, mock_browser, mock_context, mock_process


async def test_get_context_launches_browser_when_devtools_not_ready(tmp_path):
    mock_pw, mock_playwright, _mock_browser, mock_context, mock_process = _make_cdp_mocks()
    config = {**CONFIG, "browser_session_dir": str(tmp_path)}
    with (
        patch("moonlighter.core.browser.async_playwright", return_value=mock_pw),
        patch("moonlighter.core.browser.subprocess.Popen", return_value=mock_process) as popen,
        patch("moonlighter.core.browser._read_devtools_port", side_effect=[None, 9333]),
        patch("moonlighter.core.browser._devtools_ready", return_value=True),
        patch("moonlighter.core.browser.asyncio.sleep", new=AsyncMock()),
    ):
        browser_context = await browser.get_context(config)
    assert browser_context is mock_context
    popen.assert_called_once()
    mock_playwright.chromium.connect_over_cdp.assert_called_once()
    assert "9333" in mock_playwright.chromium.connect_over_cdp.call_args.args[0]


async def test_get_context_skips_launch_when_devtools_already_ready(tmp_path):
    mock_pw, mock_playwright, _mock_browser, mock_context, mock_process = _make_cdp_mocks()
    config = {**CONFIG, "browser_session_dir": str(tmp_path)}
    with (
        patch("moonlighter.core.browser.async_playwright", return_value=mock_pw),
        patch("moonlighter.core.browser.subprocess.Popen", return_value=mock_process) as popen,
        patch("moonlighter.core.browser._read_devtools_port", return_value=9222),
        patch("moonlighter.core.browser._devtools_ready", return_value=True),
    ):
        browser_context = await browser.get_context(config)
    assert browser_context is mock_context
    popen.assert_not_called()  # browser was already up, on the port that's ALREADY ours
    mock_playwright.chromium.connect_over_cdp.assert_called_once()
    assert "9222" in mock_playwright.chromium.connect_over_cdp.call_args.args[0]


async def test_get_context_reuses_connected_browser():
    _, _, mock_browser, mock_context, _ = _make_cdp_mocks()
    browser._browser = mock_browser
    with (
        patch("moonlighter.core.browser.async_playwright") as async_playwright_patch,
        patch("moonlighter.core.browser.subprocess.Popen") as popen,
    ):
        browser_context = await browser.get_context(CONFIG)
    assert browser_context is mock_context
    async_playwright_patch.assert_not_called()
    popen.assert_not_called()


async def test_get_context_passes_cdp_url_and_slow_mo(tmp_path):
    mock_pw, mock_playwright, _, _, mock_process = _make_cdp_mocks()
    config = {**CONFIG, "slow_mo_ms": 123, "browser_session_dir": str(tmp_path)}
    with (
        patch("moonlighter.core.browser.async_playwright", return_value=mock_pw),
        patch("moonlighter.core.browser.subprocess.Popen", return_value=mock_process),
        patch("moonlighter.core.browser._read_devtools_port", return_value=9444),
        patch("moonlighter.core.browser._devtools_ready", return_value=True),
    ):
        await browser.get_context(config)
    call = mock_playwright.chromium.connect_over_cdp.call_args
    assert "9444" in call.args[0]
    assert call.kwargs["slow_mo"] == 123


async def test_get_context_creates_session_dir(tmp_path):
    config = {**CONFIG, "browser_session_dir": str(tmp_path / "new_session")}
    mock_pw, _, _, _, mock_process = _make_cdp_mocks()
    with (
        patch("moonlighter.core.browser.async_playwright", return_value=mock_pw),
        patch("moonlighter.core.browser.subprocess.Popen", return_value=mock_process),
        patch("moonlighter.core.browser._read_devtools_port", return_value=9555),
        patch("moonlighter.core.browser._devtools_ready", return_value=True),
    ):
        await browser.get_context(config)
    assert (tmp_path / "new_session").exists()


async def test_get_context_raises_when_browser_never_ready(tmp_path):
    mock_pw, _, _, _, mock_process = _make_cdp_mocks()
    config = {**CONFIG, "browser_session_dir": str(tmp_path)}
    with (
        patch("moonlighter.core.browser.async_playwright", return_value=mock_pw),
        patch("moonlighter.core.browser.subprocess.Popen", return_value=mock_process),
        patch("moonlighter.core.browser._read_devtools_port", return_value=None),
        patch("moonlighter.core.browser.asyncio.sleep", new=AsyncMock()),
        pytest.raises(RuntimeError, match="Browser"),
    ):
        await browser.get_context(config)
    mock_process.kill.assert_called_once()  # cleanup of the hung process


async def test_get_context_logs_cdp_connected(caplog, tmp_path):
    """get_context() must log 'CDP connected' when it connects successfully."""
    mock_pw, _mock_playwright, _mock_browser, _mock_context, mock_process = _make_cdp_mocks()
    config = {**CONFIG, "browser_session_dir": str(tmp_path)}

    with (
        patch("moonlighter.core.browser.async_playwright", return_value=mock_pw),
        patch("moonlighter.core.browser.subprocess.Popen", return_value=mock_process),
        patch("moonlighter.core.browser._read_devtools_port", return_value=9777),
        patch("moonlighter.core.browser._devtools_ready", return_value=True),
        caplog.at_level(logging.INFO, logger="moonlighter.core.browser"),
    ):
        await browser.get_context(config)

    assert "CDP connected" in caplog.text


async def test_new_page_returns_page_from_context(tmp_path):
    mock_pw, _, _, mock_context, mock_process = _make_cdp_mocks()
    mock_page = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    config = {**CONFIG, "browser_session_dir": str(tmp_path)}
    with (
        patch("moonlighter.core.browser.async_playwright", return_value=mock_pw),
        patch("moonlighter.core.browser.subprocess.Popen", return_value=mock_process),
        patch("moonlighter.core.browser._read_devtools_port", return_value=9666),
        patch("moonlighter.core.browser._devtools_ready", return_value=True),
    ):
        page = await browser.new_page(config)
    assert page is mock_page
