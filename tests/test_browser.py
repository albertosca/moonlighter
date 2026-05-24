import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import candidatador.browser as browser_mod


_CONFIG = {
    "browser_session_dir": "/tmp/test_browser_session",
    "brave_path": "/usr/bin/brave",
    "slow_mo_ms": 0,
    "screenshots_dir": "/tmp/test_screenshots",
}


@pytest.fixture(autouse=True)
def reset_browser_globals():
    """Reset module-level singletons before each test."""
    browser_mod._playwright = None
    browser_mod._context = None
    yield
    browser_mod._playwright = None
    browser_mod._context = None


def _make_playwright_mock():
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=MagicMock())

    mock_chromium = MagicMock()
    mock_chromium.launch_persistent_context = AsyncMock(return_value=mock_context)

    mock_playwright = MagicMock()
    mock_playwright.chromium = mock_chromium
    mock_playwright.stop = AsyncMock()

    mock_pw_instance = AsyncMock()
    mock_pw_instance.start = AsyncMock(return_value=mock_playwright)
    mock_pw_instance.__aenter__ = AsyncMock(return_value=mock_playwright)

    return mock_pw_instance, mock_playwright, mock_context


# ── get_context ───────────────────────────────────────────────────────────────

async def test_get_context_creates_playwright_on_first_call():
    mock_pw_instance, mock_playwright, mock_context = _make_playwright_mock()
    with patch("candidatador.browser.async_playwright", return_value=mock_pw_instance):
        ctx = await browser_mod.get_context(_CONFIG)
    assert ctx is mock_context
    mock_playwright.chromium.launch_persistent_context.assert_called_once()


async def test_get_context_reuses_existing_context():
    mock_pw_instance, mock_playwright, mock_context = _make_playwright_mock()
    with patch("candidatador.browser.async_playwright", return_value=mock_pw_instance):
        ctx1 = await browser_mod.get_context(_CONFIG)
        ctx2 = await browser_mod.get_context(_CONFIG)
    assert ctx1 is ctx2
    # launch_persistent_context only called once despite two get_context calls
    assert mock_playwright.chromium.launch_persistent_context.call_count == 1


async def test_get_context_passes_brave_path_and_slow_mo():
    mock_pw_instance, mock_playwright, mock_context = _make_playwright_mock()
    with patch("candidatador.browser.async_playwright", return_value=mock_pw_instance):
        await browser_mod.get_context(_CONFIG)
    call_kwargs = mock_playwright.chromium.launch_persistent_context.call_args.kwargs
    assert call_kwargs["executable_path"] == _CONFIG["brave_path"]
    assert call_kwargs["slow_mo"] == _CONFIG["slow_mo_ms"]


async def test_get_context_creates_session_dir(tmp_path):
    config = {**_CONFIG, "browser_session_dir": str(tmp_path / "new_session")}
    mock_pw_instance, _, _ = _make_playwright_mock()
    with patch("candidatador.browser.async_playwright", return_value=mock_pw_instance):
        await browser_mod.get_context(config)
    assert (tmp_path / "new_session").exists()


# ── new_page ──────────────────────────────────────────────────────────────────

async def test_new_page_returns_page_from_context():
    mock_pw_instance, _, mock_context = _make_playwright_mock()
    mock_page = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    with patch("candidatador.browser.async_playwright", return_value=mock_pw_instance):
        page = await browser_mod.new_page(_CONFIG)
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


# ── close ─────────────────────────────────────────────────────────────────────

async def test_close_stops_playwright_and_clears_globals():
    mock_context = AsyncMock()
    mock_playwright = MagicMock()
    mock_playwright.stop = AsyncMock()

    browser_mod._context = mock_context
    browser_mod._playwright = mock_playwright

    await browser_mod.close()

    mock_context.close.assert_called_once()
    mock_playwright.stop.assert_called_once()
    assert browser_mod._context is None
    assert browser_mod._playwright is None


async def test_close_is_idempotent_when_already_closed():
    browser_mod._context = None
    browser_mod._playwright = None
    await browser_mod.close()  # should not raise
