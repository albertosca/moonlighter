from unittest.mock import AsyncMock, MagicMock, patch

import gauntler.core.browser as browser_mod
import pytest

_CONFIG = {
    "browser_session_dir": "/tmp/test_browser_session",
    "browser_path": "/usr/bin/brave",
    "slow_mo_ms": 0,
    "screenshots_dir": "/tmp/test_screenshots",
}


@pytest.fixture(autouse=True)
def reset_browser_globals():
    """Reset module-level singletons before each test."""
    browser_mod._playwright = None
    browser_mod._browser = None
    browser_mod._browser_process = None
    yield
    browser_mod._playwright = None
    browser_mod._browser = None
    browser_mod._browser_process = None


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


# ── _read_devtools_port (S-03: real filesystem behavior, no mocks) ────────────


def test_read_devtools_port_parses_first_line(tmp_path):
    port_file = tmp_path / "DevToolsActivePort"
    port_file.write_text("54321\n/devtools/browser/abc-123\n")
    assert browser_mod._read_devtools_port(tmp_path) == 54321


def test_read_devtools_port_missing_file_returns_none(tmp_path):
    assert browser_mod._read_devtools_port(tmp_path) is None


def test_read_devtools_port_malformed_content_returns_none(tmp_path):
    port_file = tmp_path / "DevToolsActivePort"
    port_file.write_text("not-a-port\n")
    assert browser_mod._read_devtools_port(tmp_path) is None


def test_read_devtools_port_empty_file_returns_none(tmp_path):
    port_file = tmp_path / "DevToolsActivePort"
    port_file.write_text("")
    assert browser_mod._read_devtools_port(tmp_path) is None


# ── _launch_browser ────────────────────────────────────────────────────────────


async def test_launch_browser_uses_random_port_flag(tmp_path):
    mock_proc = MagicMock()
    mock_proc.kill = MagicMock()
    with (
        patch("gauntler.core.browser.subprocess.Popen", return_value=mock_proc) as popen,
        patch("gauntler.core.browser._read_devtools_port", side_effect=[None, 9333]),
        patch("gauntler.core.browser._devtools_ready", return_value=True),
    ):
        port = await browser_mod._launch_browser(_CONFIG, tmp_path)
    assert port == 9333
    launch_args = popen.call_args.args[0]
    assert "--remote-debugging-port=0" in launch_args
    assert not any(a.startswith("--remote-debugging-port=9222") for a in launch_args)


async def test_launch_browser_deletes_stale_port_file_before_launch(tmp_path):
    """A leftover DevToolsActivePort from a dead session must never be trusted —
    it's deleted before the new process starts, so a crashed launch can't
    silently reconnect to a stale/foreign port (S-03)."""
    stale = tmp_path / "DevToolsActivePort"
    stale.write_text("11111\n/devtools/browser/stale\n")
    mock_proc = MagicMock()
    mock_proc.kill = MagicMock()

    with (
        patch("gauntler.core.browser.subprocess.Popen", return_value=mock_proc),
        patch("gauntler.core.browser._read_devtools_port", return_value=None),
        patch("gauntler.core.browser.asyncio.sleep", new=AsyncMock()),
        pytest.raises(RuntimeError),
    ):
        await browser_mod._launch_browser(_CONFIG, tmp_path)

    assert not stale.exists()


async def test_launch_browser_raises_when_port_never_appears(tmp_path):
    mock_proc = MagicMock()
    mock_proc.kill = MagicMock()
    with (
        patch("gauntler.core.browser.subprocess.Popen", return_value=mock_proc),
        patch("gauntler.core.browser._read_devtools_port", return_value=None),
        patch("gauntler.core.browser.asyncio.sleep", new=AsyncMock()),
        pytest.raises(RuntimeError, match="Browser"),
    ):
        await browser_mod._launch_browser(_CONFIG, tmp_path)
    mock_proc.kill.assert_called_once()


# ── get_context ───────────────────────────────────────────────────────────────


async def test_get_context_launches_browser_when_devtools_not_ready(tmp_path):
    mock_pw, mock_playwright, _mock_browser, mock_context, mock_proc = _make_cdp_mocks()
    config = {**_CONFIG, "browser_session_dir": str(tmp_path)}
    with (
        patch("gauntler.core.browser.async_playwright", return_value=mock_pw),
        patch("gauntler.core.browser.subprocess.Popen", return_value=mock_proc) as popen,
        patch("gauntler.core.browser._read_devtools_port", side_effect=[None, 9333]),
        patch("gauntler.core.browser._devtools_ready", return_value=True),
        patch("gauntler.core.browser.asyncio.sleep", new=AsyncMock()),
    ):
        ctx = await browser_mod.get_context(config)
    assert ctx is mock_context
    popen.assert_called_once()
    mock_playwright.chromium.connect_over_cdp.assert_called_once()
    assert "9333" in mock_playwright.chromium.connect_over_cdp.call_args.args[0]


async def test_get_context_skips_launch_when_devtools_already_ready(tmp_path):
    mock_pw, mock_playwright, _mock_browser, mock_context, mock_proc = _make_cdp_mocks()
    config = {**_CONFIG, "browser_session_dir": str(tmp_path)}
    with (
        patch("gauntler.core.browser.async_playwright", return_value=mock_pw),
        patch("gauntler.core.browser.subprocess.Popen", return_value=mock_proc) as popen,
        patch("gauntler.core.browser._read_devtools_port", return_value=9222),
        patch("gauntler.core.browser._devtools_ready", return_value=True),
    ):
        ctx = await browser_mod.get_context(config)
    assert ctx is mock_context
    popen.assert_not_called()  # browser já estava de pé, na porta que JÁ é nossa
    mock_playwright.chromium.connect_over_cdp.assert_called_once()
    assert "9222" in mock_playwright.chromium.connect_over_cdp.call_args.args[0]


async def test_get_context_reuses_connected_browser():
    _, _, mock_browser, mock_context, _ = _make_cdp_mocks()
    browser_mod._browser = mock_browser
    with (
        patch("gauntler.core.browser.async_playwright") as pw,
        patch("gauntler.core.browser.subprocess.Popen") as popen,
    ):
        ctx = await browser_mod.get_context(_CONFIG)
    assert ctx is mock_context
    pw.assert_not_called()
    popen.assert_not_called()


async def test_get_context_passes_cdp_url_and_slow_mo(tmp_path):
    mock_pw, mock_playwright, _, _, mock_proc = _make_cdp_mocks()
    config = {**_CONFIG, "slow_mo_ms": 123, "browser_session_dir": str(tmp_path)}
    with (
        patch("gauntler.core.browser.async_playwright", return_value=mock_pw),
        patch("gauntler.core.browser.subprocess.Popen", return_value=mock_proc),
        patch("gauntler.core.browser._read_devtools_port", return_value=9444),
        patch("gauntler.core.browser._devtools_ready", return_value=True),
    ):
        await browser_mod.get_context(config)
    call = mock_playwright.chromium.connect_over_cdp.call_args
    assert "9444" in call.args[0]
    assert call.kwargs["slow_mo"] == 123


async def test_get_context_creates_session_dir(tmp_path):
    config = {**_CONFIG, "browser_session_dir": str(tmp_path / "new_session")}
    mock_pw, _, _, _, mock_proc = _make_cdp_mocks()
    with (
        patch("gauntler.core.browser.async_playwright", return_value=mock_pw),
        patch("gauntler.core.browser.subprocess.Popen", return_value=mock_proc),
        patch("gauntler.core.browser._read_devtools_port", return_value=9555),
        patch("gauntler.core.browser._devtools_ready", return_value=True),
    ):
        await browser_mod.get_context(config)
    assert (tmp_path / "new_session").exists()


async def test_get_context_raises_when_browser_never_ready(tmp_path):
    mock_pw, _, _, _, mock_proc = _make_cdp_mocks()
    config = {**_CONFIG, "browser_session_dir": str(tmp_path)}
    with (
        patch("gauntler.core.browser.async_playwright", return_value=mock_pw),
        patch("gauntler.core.browser.subprocess.Popen", return_value=mock_proc),
        patch("gauntler.core.browser._read_devtools_port", return_value=None),
        patch("gauntler.core.browser.asyncio.sleep", new=AsyncMock()),
        pytest.raises(RuntimeError, match="Browser"),
    ):
        await browser_mod.get_context(config)
    mock_proc.kill.assert_called_once()  # cleanup do processo travado


# ── new_page ──────────────────────────────────────────────────────────────────


async def test_new_page_returns_page_from_context(tmp_path):
    mock_pw, _, _, mock_context, mock_proc = _make_cdp_mocks()
    mock_page = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    config = {**_CONFIG, "browser_session_dir": str(tmp_path)}
    with (
        patch("gauntler.core.browser.async_playwright", return_value=mock_pw),
        patch("gauntler.core.browser.subprocess.Popen", return_value=mock_proc),
        patch("gauntler.core.browser._read_devtools_port", return_value=9666),
        patch("gauntler.core.browser._devtools_ready", return_value=True),
    ):
        page = await browser_mod.new_page(config)
    assert page is mock_page


# ── save_screenshot ───────────────────────────────────────────────────────────


async def test_save_screenshot_calls_page_screenshot(tmp_path):
    config = {**_CONFIG, "screenshots_dir": str(tmp_path)}
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock()
    path = await browser_mod.save_screenshot(mock_page, job_id=42, step="fill", config=config)
    mock_page.screenshot.assert_called_once_with(path=path)
    assert "42" in path
    assert "fill" in path


async def test_save_screenshot_creates_job_subdir(tmp_path):
    config = {**_CONFIG, "screenshots_dir": str(tmp_path)}
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock()
    await browser_mod.save_screenshot(mock_page, job_id=99, step="submit", config=config)
    assert (tmp_path / "99").is_dir()


# ── hide_window / show_window ──────────────────────────────────────────────


async def test_hide_window_minimizes_via_cdp():
    mock_page = MagicMock()
    mock_cdp = AsyncMock()
    mock_cdp.send = AsyncMock(side_effect=[{"windowId": 7}, None])
    mock_page.context.new_cdp_session = AsyncMock(return_value=mock_cdp)

    await browser_mod.hide_window(mock_page)

    mock_cdp.send.assert_any_call("Browser.getWindowForTarget")
    mock_cdp.send.assert_any_call(
        "Browser.setWindowBounds",
        {"windowId": 7, "bounds": {"windowState": "minimized"}},
    )


async def test_show_window_restores_via_cdp():
    mock_page = MagicMock()
    mock_cdp = AsyncMock()
    mock_cdp.send = AsyncMock(side_effect=[{"windowId": 3}, None])
    mock_page.context.new_cdp_session = AsyncMock(return_value=mock_cdp)

    await browser_mod.show_window(mock_page)

    mock_cdp.send.assert_any_call("Browser.getWindowForTarget")
    mock_cdp.send.assert_any_call(
        "Browser.setWindowBounds",
        {"windowId": 3, "bounds": {"windowState": "normal"}},
    )


# ── close ─────────────────────────────────────────────────────────────────────


async def test_close_stops_everything_and_clears_globals():
    mock_browser = MagicMock()
    mock_browser.close = AsyncMock()
    mock_playwright = MagicMock()
    mock_playwright.stop = AsyncMock()
    mock_process = MagicMock()

    browser_mod._browser = mock_browser
    browser_mod._playwright = mock_playwright
    browser_mod._browser_process = mock_process

    await browser_mod.close()

    mock_browser.close.assert_called_once()
    mock_playwright.stop.assert_called_once()
    mock_process.terminate.assert_called_once()
    assert browser_mod._browser is None
    assert browser_mod._playwright is None
    assert browser_mod._browser_process is None


async def test_close_is_idempotent_when_already_closed():
    browser_mod._browser = None
    browser_mod._playwright = None
    browser_mod._browser_process = None
    await browser_mod.close()  # should not raise


async def test_get_context_logs_cdp_connected(caplog, tmp_path):
    """get_context() deve logar 'CDP connected' quando conecta com sucesso."""
    import logging

    mock_pw, _mock_playwright, _mock_browser, _mock_context, mock_proc = _make_cdp_mocks()
    config = {**_CONFIG, "browser_session_dir": str(tmp_path)}

    with (
        patch("gauntler.core.browser.async_playwright", return_value=mock_pw),
        patch("gauntler.core.browser.subprocess.Popen", return_value=mock_proc),
        patch("gauntler.core.browser._read_devtools_port", return_value=9777),
        patch("gauntler.core.browser._devtools_ready", return_value=True),
        caplog.at_level(logging.INFO, logger="gauntler.core.browser"),
    ):
        await browser_mod.get_context(config)

    assert "CDP connected" in caplog.text
