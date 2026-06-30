from pathlib import Path

import pytest
from candidatador.core.config import browser_executable, load_config
from playwright.async_api import async_playwright


@pytest.fixture(scope="module")
def fixtures_dir():
    return Path(__file__).parent / "fixtures"


async def _launch(pw):
    """
    Lança um Chromium headless. Prefere o browser do usuário (mesmo binário que o
    app de verdade usa) via executable_path; cai no Chromium bundled do Playwright
    se não existir. Perfil temporário e isolado — NÃO toca na sessão real.
    """
    browser_path = browser_executable(load_config())
    if browser_path and Path(browser_path).exists():
        return await pw.chromium.launch(headless=True, executable_path=browser_path)
    # Fallback: Chromium bundled (exige `playwright install chromium`).
    return await pw.chromium.launch(headless=True)


@pytest.fixture
async def browser_page(fixtures_dir):
    """Página Chromium headless (Brave do usuário, ou bundled como fallback),
    servindo as fixtures via file:// URLs."""
    async with async_playwright() as pw:
        try:
            browser = await _launch(pw)
        except Exception as e:
            pytest.skip(
                f"Sem navegador para e2e (Brave ausente e Chromium bundled não "
                f"instalado — rode `playwright install chromium`): {e}"
            )
        page = await browser.new_page()
        yield page, f"file://{fixtures_dir}"
        await browser.close()
