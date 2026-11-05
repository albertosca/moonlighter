"""close stops the driver and ends the browser process; detach stops only the driver and leaves the browser running for the human."""

from unittest.mock import AsyncMock, MagicMock

from moonlighter.core import browser


async def test_close_stops_everything_and_clears_globals():
    mock_browser = MagicMock()
    mock_browser.close = AsyncMock()
    mock_playwright = MagicMock()
    mock_playwright.stop = AsyncMock()
    mock_process = MagicMock()

    browser._browser = mock_browser
    browser._playwright = mock_playwright
    browser._browser_process = mock_process

    await browser.close()

    mock_browser.close.assert_called_once()
    mock_playwright.stop.assert_called_once()
    mock_process.terminate.assert_called_once()
    assert browser._browser is None
    assert browser._playwright is None
    assert browser._browser_process is None


async def test_close_is_idempotent_when_already_closed():
    browser._browser = None
    browser._playwright = None
    browser._browser_process = None
    await browser.close()  # should not raise


async def test_detach_disconnects_playwright_but_leaves_the_browser_running():
    """A captcha token minted in a CDP-controlled tab does not validate
    server-side, so handing the page back means genuinely letting go: stop the
    Playwright driver, keep the window and its filled form alive for the human.
    Killing the process would throw away the work.
    """
    mock_browser = MagicMock()
    mock_browser.close = AsyncMock()
    mock_pw = MagicMock()
    mock_pw.stop = AsyncMock()
    mock_process = MagicMock()

    browser._browser = mock_browser
    browser._playwright = mock_pw
    browser._browser_process = mock_process

    await browser.detach()

    mock_browser.close.assert_awaited_once()
    mock_pw.stop.assert_awaited_once()
    mock_process.terminate.assert_not_called()
    mock_process.kill.assert_not_called()
    assert browser._browser is None
    assert browser._playwright is None
    assert browser._browser_process is mock_process


async def test_detach_is_safe_when_nothing_is_connected():
    browser._browser = None
    browser._playwright = None
    await browser.detach()


async def test_detach_forgets_the_connection_even_if_closing_fails():
    """A driver that errors on the way out must not leave a stale handle behind —
    the next operation would reuse a dead connection.
    """
    mock_browser = MagicMock()
    mock_browser.close = AsyncMock(side_effect=RuntimeError("already gone"))
    mock_pw = MagicMock()
    mock_pw.stop = AsyncMock(side_effect=RuntimeError("nope"))
    browser._browser = mock_browser
    browser._playwright = mock_pw

    await browser.detach()

    assert browser._browser is None
    assert browser._playwright is None
