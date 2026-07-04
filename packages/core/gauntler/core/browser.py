import asyncio
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from gauntler.core.config import browser_executable
from gauntler.core.log import get_logger
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

logger = get_logger(__name__)

_playwright: Any = None
_browser: Browser | None = None
_browser_process: subprocess.Popen[bytes] | None = None

_DEBUG_PORT = 9222


def _devtools_ready() -> bool:
    try:
        urllib.request.urlopen(f"http://localhost:{_DEBUG_PORT}/json/version", timeout=1)
        return True
    except Exception:
        return False


async def _first_or_new_context(browser: Browser) -> BrowserContext:
    return browser.contexts[0] if browser.contexts else await browser.new_context()


async def _launch_browser(config: dict[str, Any], session_dir: Path) -> None:
    """Sobe o browser (Chrome/Chromium/Brave) com a porta de debug e espera o
    DevTools responder (até 30s)."""
    global _browser_process
    logger.info("Launching browser on port %d", _DEBUG_PORT)
    _browser_process = subprocess.Popen(
        [
            browser_executable(config),
            f"--remote-debugging-port={_DEBUG_PORT}",
            f"--user-data-dir={session_dir}",
            "--no-first-run",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        if _devtools_ready():
            return
        await asyncio.sleep(0.5)
    _browser_process.kill()
    _browser_process = None
    raise RuntimeError(f"Browser não ficou disponível na porta {_DEBUG_PORT} em 30s")


async def get_context(config: dict[str, Any]) -> BrowserContext:
    """Return a browser context via CDP. Launches the browser if not running."""
    global _playwright, _browser

    if _browser is not None and _browser.is_connected():
        return await _first_or_new_context(_browser)

    session_dir = Path(config["browser_session_dir"]).expanduser()
    session_dir.mkdir(parents=True, exist_ok=True)
    if not _devtools_ready():
        await _launch_browser(config, session_dir)

    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.connect_over_cdp(
        f"http://localhost:{_DEBUG_PORT}",
        slow_mo=config.get("slow_mo_ms", 300),
    )
    logger.info("CDP connected")
    return await _first_or_new_context(_browser)


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


async def _set_window_state(page: Page, window_state: str) -> None:
    cdp = await page.context.new_cdp_session(page)
    target_info = await cdp.send("Browser.getWindowForTarget")
    await cdp.send(
        "Browser.setWindowBounds",
        {"windowId": target_info["windowId"], "bounds": {"windowState": window_state}},
    )


async def hide_window(page: Page) -> None:
    """Minimize the browser window via CDP. Idempotent."""
    await _set_window_state(page, "minimized")


async def show_window(page: Page) -> None:
    """Restore and focus the browser window via CDP. Idempotent."""
    await _set_window_state(page, "normal")


async def close() -> None:
    global _playwright, _browser, _browser_process
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    if _browser_process:
        _browser_process.terminate()
        _browser_process = None
