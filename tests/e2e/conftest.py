from pathlib import Path

import pytest
from gauntler.core.config import browser_executable, load_config
from playwright.async_api import async_playwright


@pytest.fixture(scope="module")
def fixtures_dir():
    return Path(__file__).parent / "fixtures"


async def _launch(pw):
    """
    Launches a headless Chromium. Prefers the user's browser (the same binary the
    real app uses) via executable_path; falls back to Playwright's bundled Chromium
    if it doesn't exist. Temporary, isolated profile — does NOT touch the real session.
    """
    browser_path = browser_executable(load_config())
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
