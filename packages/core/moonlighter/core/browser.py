"""The browser session: one Chromium-family browser per process, driven over CDP.

Launches the operator's browser on an OS-chosen debug port, or reuses the one
already running from our own user-data-dir, and connects Playwright to it.
detach() lets go and leaves the browser running for the human; close() ends
it. Per-page window state lives in `browser_window`.
"""

import asyncio
import contextlib
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from moonlighter.core.config.paths import browser_executable
from moonlighter.core.log import get_logger

logger = get_logger(__name__)

_playwright: Any = None
_browser: Browser | None = None
_browser_process: subprocess.Popen[bytes] | None = None

_DEVTOOLS_PORT_FILE = "DevToolsActivePort"


def _read_devtools_port(session_directory: Path) -> int | None:
    """Read the port Chromium chose for --remote-debugging-port=0.

    Chromium writes it to the DevToolsActivePort file inside OUR OWN
    user-data-dir (S-03). None if the file doesn't exist yet or is malformed
    (browser still starting up) — we never trust a fixed port nor "whatever
    answers" on a known port.
    """
    port_file = session_directory / _DEVTOOLS_PORT_FILE
    if not port_file.exists():
        return None
    try:
        first_line = port_file.read_text().splitlines()[0]
        return int(first_line)
    except IndexError, ValueError:
        return None


def _devtools_ready(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=1)
    except Exception:  # noqa: BLE001 - any failure to answer (refused, timed out, reset, an HTTP error) means "not ready yet"
        return False
    else:
        return True


async def _first_or_new_context(browser: Browser) -> BrowserContext:
    return browser.contexts[0] if browser.contexts else await browser.new_context()


async def _launch_browser(config: dict[str, Any], session_directory: Path) -> int:
    """Launch the browser (Chrome/Chromium/Brave) and return its debug port.

    The port is RANDOM, chosen by the OS itself (--remote-debugging-port=0),
    and the real one is read from DevToolsActivePort inside OUR OWN
    user-data-dir (S-03) — never a fixed port, and never "whatever answers":
    the port comes from a file that only the process we just launched writes.
    """
    global _browser_process  # noqa: PLW0603 - one browser per process, so the session lives in module singletons
    port_file = session_directory / _DEVTOOLS_PORT_FILE
    port_file.unlink(missing_ok=True)  # discard the port from a previous dead session

    logger.info("Launching browser (random debug port)")
    # S603: browser_executable(config) is the operator's local YAML config, which the
    # trust model treats as trusted input -- never reachable from scraped job text, ATS
    # DOM, or email bodies. See specs/2026-07-09-security-audit-findings.md ("Trust model").
    _browser_process = subprocess.Popen(  # noqa: ASYNC220, S603 - Popen returns once the process is spawned and nothing here waits on it; the executable is trusted config (see above)
        [
            browser_executable(config),
            "--remote-debugging-port=0",
            f"--user-data-dir={session_directory}",
            "--no-first-run",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        port = _read_devtools_port(session_directory)
        if port is not None and _devtools_ready(port):
            return port
        await asyncio.sleep(0.5)
    _browser_process.kill()
    _browser_process = None
    raise RuntimeError("Browser did not become available (DevToolsActivePort) within 30s")


async def get_context(config: dict[str, Any]) -> BrowserContext:
    """Return a browser context via CDP. Launches the browser if not running."""
    global _playwright, _browser  # noqa: PLW0603 - one browser per process, so the session lives in module singletons

    if _browser is not None and _browser.is_connected():
        return await _first_or_new_context(_browser)

    session_directory = Path(config["browser_session_dir"]).expanduser()  # noqa: ASYNC240 - expanduser resolves ~ from $HOME, no blocking I/O
    session_directory.mkdir(parents=True, exist_ok=True)
    port = _read_devtools_port(session_directory)
    if port is None or not _devtools_ready(port):
        port = await _launch_browser(config, session_directory)

    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.connect_over_cdp(
        f"http://localhost:{port}",
        slow_mo=config.get("slow_mo_ms", 300),
    )
    logger.info("CDP connected")
    return await _first_or_new_context(_browser)


async def new_page(config: dict[str, Any]) -> Page:
    context = await get_context(config)
    page = await context.new_page()
    logger.debug("new_page created")
    return page


async def detach() -> None:
    """Let go of the browser completely, leaving it running for the human.

    Unlike close(), the browser PROCESS survives — the window, its tabs and a
    filled-in form stay exactly as they are. Only the Playwright driver goes
    away, so the page stops being automation-controlled.

    This exists for captcha: a token minted inside a CDP-controlled tab does not
    validate server-side (Recruitee answers HTTP 422 on captchaToken), so the
    only honest handover is to actually stop driving. Errors on the way out are
    swallowed, but the handles are cleared regardless — a stale connection would
    be reused by the next call.
    """
    global _playwright, _browser  # noqa: PLW0603 - one browser per process, so the session lives in module singletons
    if _browser:
        with contextlib.suppress(Exception):
            await _browser.close()
        _browser = None
    if _playwright:
        with contextlib.suppress(Exception):
            await _playwright.stop()
        _playwright = None
    logger.info("browser: detached — no longer automation-controlled")


async def close() -> None:
    global _playwright, _browser, _browser_process  # noqa: PLW0603 - one browser per process, so the session lives in module singletons
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    if _browser_process:
        _browser_process.terminate()
        _browser_process = None
