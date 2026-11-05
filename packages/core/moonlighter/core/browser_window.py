"""Per-page window state over CDP: minimize, restore, and screenshot around it.

Each call drives one `Page` through a CDP session of its own and touches none
of the session singletons in `browser`.
"""

import contextlib
from pathlib import Path
from typing import Any

from playwright.async_api import Page


async def save_screenshot(page: Page, *, job_id: int, step: str, config: dict[str, Any]) -> str:
    """Capture the page, restoring a minimized window for the duration.

    `page.screenshot()` captures from the compositor surface, and a minimized
    window produces no new frames — the call then blocks until it times out.
    The browser-driven filler this predates minimized the window before
    filling, which made the 03-filled review artifact impossible to produce,
    on every ATS. Reproduced on both Greenhouse and Recruitee; `fromSurface:
    False` was measured as an alternative and took 175s, so restoring around
    the capture it is. Kept for browser-based extensions (e.g. LinkedIn
    scanning) that still drive a page — the assisted flow that replaced the
    in-repo filler never opens a browser.

    The window is put back exactly as it was, so the two screenshots taken with
    the window deliberately visible are not minimized as a side effect. Every
    window-state call is best-effort (like the teardown in `browser.detach`):
    losing the minimized posture must never cost us the screenshot.
    """
    screenshots_directory = Path(config["screenshots_dir"]) / str(job_id)
    screenshots_directory.mkdir(parents=True, exist_ok=True)
    path = str(screenshots_directory / f"{step}.png")

    cdp = None
    window_id = None
    with contextlib.suppress(Exception):
        cdp = await page.context.new_cdp_session(page)
        info = await cdp.send("Browser.getWindowForTarget")
        if info.get("bounds", {}).get("windowState") == "minimized":
            window_id = info["windowId"]
            await cdp.send(
                "Browser.setWindowBounds",
                {"windowId": window_id, "bounds": {"windowState": "normal"}},
            )
    try:
        # full_page, because this is a review artifact: the viewport is ~750 CSS
        # px and a real application form runs to ~4500, so a viewport capture
        # showed 17% of it — asking a human to approve what they cannot see.
        await page.screenshot(path=path, full_page=True)
    finally:
        if cdp is not None and window_id is not None:
            with contextlib.suppress(Exception):
                await cdp.send(
                    "Browser.setWindowBounds",
                    {"windowId": window_id, "bounds": {"windowState": "minimized"}},
                )
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
