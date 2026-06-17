import os

import pytest
from playwright.async_api import async_playwright

from candidatador.config import load_config


@pytest.fixture(scope="module")
def fixtures_dir():
    return os.path.join(os.path.dirname(__file__), "fixtures")


async def _launch(pw):
    """
    Lança um Chromium headless. Prefere o Brave do usuário (mesmo binário que o
    app de verdade usa) via executable_path; cai no Chromium bundled do Playwright
    se o Brave não existir. Perfil temporário e isolado — NÃO toca na sessão real.
    """
    brave_path = load_config().get("brave_path", "")
    if brave_path and os.path.exists(brave_path):
        return await pw.chromium.launch(headless=True, executable_path=brave_path)
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
