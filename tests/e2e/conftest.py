import pytest
import os
import shutil
from playwright.async_api import async_playwright


@pytest.fixture(scope="module")
def fixtures_dir():
    return os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
async def browser_page(fixtures_dir):
    """Playwright chromium headless page, serving fixtures via file:// URLs."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        yield page, f"file://{fixtures_dir}"
        await browser.close()
