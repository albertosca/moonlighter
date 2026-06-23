import asyncio
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from candidatador.core.log import get_logger

logger = get_logger(__name__)

_playwright: Any = None
_browser: Browser | None = None
_brave_process: subprocess.Popen[bytes] | None = None

_DEBUG_PORT = 9222


def _devtools_ready() -> bool:
    try:
        urllib.request.urlopen(f"http://localhost:{_DEBUG_PORT}/json/version", timeout=1)
        return True
    except Exception:
        return False


async def get_context(config: dict[str, Any]) -> BrowserContext:
    """Return a Brave browser context via CDP. Launches Brave if not running."""
    global _playwright, _browser, _brave_process

    if _browser is not None and _browser.is_connected():
        contexts = _browser.contexts
        return contexts[0] if contexts else await _browser.new_context()

    session_dir = Path(config["browser_session_dir"]).expanduser()
    session_dir.mkdir(parents=True, exist_ok=True)

    if not _devtools_ready():
        logger.info("Launching Brave on port %d", _DEBUG_PORT)
        _brave_process = subprocess.Popen(
            [
                config["brave_path"],
                f"--remote-debugging-port={_DEBUG_PORT}",
                f"--user-data-dir={session_dir}",
                "--no-first-run",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(60):
            if _devtools_ready():
                break
            await asyncio.sleep(0.5)
        else:
            _brave_process.kill()
            _brave_process = None
            raise RuntimeError(f"Brave não ficou disponível na porta {_DEBUG_PORT} em 30s")

    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.connect_over_cdp(
        f"http://localhost:{_DEBUG_PORT}",
        slow_mo=config.get("slow_mo_ms", 300),
    )
    logger.info("CDP connected")

    contexts = _browser.contexts
    return contexts[0] if contexts else await _browser.new_context()


async def new_page(config: dict[str, Any]) -> Page:
    context = await get_context(config)
    page = await context.new_page()
    logger.debug("new_page created")
    return page


async def save_screenshot(page: Page, job_id: int, step: str, config: dict[str, Any]) -> str:
    screenshots_dir = Path(config["screenshots_dir"]) / str(job_id)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    path = str(screenshots_dir / f"{step}.png")
    await page.screenshot(path=path)
    return path


async def close() -> None:
    global _playwright, _browser, _brave_process
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    if _brave_process:
        _brave_process.terminate()
        _brave_process = None
