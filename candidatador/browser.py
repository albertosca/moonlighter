from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, BrowserContext, Page

_playwright = None
_context: Optional[BrowserContext] = None


async def get_context(config: dict) -> BrowserContext:
    """Return a persistent Brave browser context. Creates it once, reuses across calls."""
    global _playwright, _context
    if _context is not None:
        return _context

    session_dir = Path(config["browser_session_dir"])
    session_dir.mkdir(parents=True, exist_ok=True)

    _playwright = await async_playwright().start()
    _context = await _playwright.chromium.launch_persistent_context(
        user_data_dir=str(session_dir),
        executable_path=config["brave_path"],
        headless=False,
        slow_mo=config["slow_mo_ms"],
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36 Brave/1.61"
        ),
    )
    return _context


async def new_page(config: dict) -> Page:
    context = await get_context(config)
    return await context.new_page()


async def save_screenshot(page: Page, job_id: int, step: str, config: dict) -> str:
    screenshots_dir = Path(config["screenshots_dir"]) / str(job_id)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    path = str(screenshots_dir / f"{step}.png")
    await page.screenshot(path=path)
    return path


async def close():
    global _playwright, _context
    if _context:
        await _context.close()
        _context = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
