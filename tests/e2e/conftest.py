from pathlib import Path

import pytest
from moonlighter.core.config import browser_executable, load_config
from moonlighter.init import detect_browser
from playwright.async_api import async_playwright


@pytest.fixture(scope="module")
def fixtures_dir():
    return Path(__file__).parent / "fixtures"


async def _launch(pw):
    """
    Launches a headless Chromium. Prefers the user's browser (the same binary the
    real app uses) via executable_path; falls back to Playwright's bundled Chromium
    if it doesn't exist. Temporary, isolated profile — does NOT touch the real session.

    The config is consulted first but cannot be relied on: the root conftest points
    MOONLIGHTER_HOME at a temp dir before collection, so `load_config()` here reads
    an empty config and finds no browser_path. That silently skipped the ENTIRE e2e
    suite — a green run that had exercised nothing. detect_browser() scans the usual
    install locations and does not depend on the user's home.
    """
    candidates = [browser_executable(load_config()), detect_browser()]
    for browser_path in candidates:
        if browser_path and Path(browser_path).exists():
            return await pw.chromium.launch(headless=True, executable_path=browser_path)
    # Fallback: bundled Chromium (requires `playwright install chromium`).
    return await pw.chromium.launch(headless=True)


@pytest.fixture
async def browser_page(fixtures_dir):
    """Headless Chromium page (the user's Brave, or bundled as fallback),
    serving the fixtures via file:// URLs."""
    async with async_playwright() as pw:
        try:
            browser = await _launch(pw)
        except Exception as e:
            pytest.skip(
                f"No browser available for e2e (Brave missing and bundled Chromium "
                f"not installed — run `playwright install chromium`): {e}"
            )
        page = await browser.new_page()
        yield page, f"file://{fixtures_dir}"
        await browser.close()
