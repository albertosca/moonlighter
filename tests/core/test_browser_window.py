"""save_screenshot captures the whole page around a minimized window, and hide_window and show_window set the window state over CDP."""

from unittest.mock import AsyncMock, MagicMock

from moonlighter.core import browser_window

from tests.core.browser_config import CONFIG

# ── save_screenshot ───────────────────────────────────────────────────────────


async def test_save_screenshot_captures_the_whole_page(tmp_path):
    """The viewport is ~750 CSS px; a real application form is ~4500. A
    viewport-only capture showed 17% of the form, so the human-review gate was
    asking someone to approve what they could not see. full_page is what makes
    03-filled a review artifact rather than a thumbnail.
    """
    config = {**CONFIG, "screenshots_dir": str(tmp_path)}
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock()
    path = await browser_window.save_screenshot(mock_page, job_id=42, step="fill", config=config)
    mock_page.screenshot.assert_called_once_with(path=path, full_page=True)
    assert "42" in path
    assert "fill" in path


async def test_save_screenshot_creates_job_subdir(tmp_path):
    config = {**CONFIG, "screenshots_dir": str(tmp_path)}
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock()
    await browser_window.save_screenshot(mock_page, job_id=99, step="submit", config=config)
    assert (tmp_path / "99").is_dir()


async def test_save_screenshot_restores_a_minimized_window_and_re_minimizes_it(tmp_path):
    """A minimized window produces no compositor frames, so page.screenshot()
    blocks until it times out -- reproduced on both Greenhouse and Recruitee.
    The browser-driven filler this predates minimized the window before
    filling, which made the 03-filled review artifact impossible to produce.
    Restore around the capture, then put the window back exactly as it was.
    """
    config = {**CONFIG, "screenshots_dir": str(tmp_path)}
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock()
    mock_cdp = AsyncMock()
    mock_cdp.send = AsyncMock(return_value={"windowId": 5, "bounds": {"windowState": "minimized"}})
    mock_page.context.new_cdp_session = AsyncMock(return_value=mock_cdp)

    await browser_window.save_screenshot(mock_page, job_id=1, step="03-filled", config=config)

    states = [
        call.args[1]["bounds"]["windowState"]
        for call in mock_cdp.send.call_args_list
        if call.args[0] == "Browser.setWindowBounds"
    ]
    assert states == ["normal", "minimized"], (
        f"expected restore-then-re-minimize around the capture, got {states}"
    )
    mock_page.screenshot.assert_awaited_once()


async def test_save_screenshot_leaves_an_already_visible_window_alone(tmp_path):
    """01-job-page and 02-form are taken with the window visible. Blindly
    re-minimizing after every capture would hide a window the flow means to
    keep on screen.
    """
    config = {**CONFIG, "screenshots_dir": str(tmp_path)}
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock()
    mock_cdp = AsyncMock()
    mock_cdp.send = AsyncMock(return_value={"windowId": 5, "bounds": {"windowState": "normal"}})
    mock_page.context.new_cdp_session = AsyncMock(return_value=mock_cdp)

    await browser_window.save_screenshot(mock_page, job_id=2, step="01-job-page", config=config)

    assert not [
        call for call in mock_cdp.send.call_args_list if call.args[0] == "Browser.setWindowBounds"
    ], "a visible window must not have its state touched"
    mock_page.screenshot.assert_awaited_once()


async def test_save_screenshot_still_captures_when_window_state_is_unavailable(tmp_path):
    """CDP window-state calls are best-effort, as the browser-driven filler's
    were made in 96decbc; a failure here must not cost us the screenshot itself.
    """
    config = {**CONFIG, "screenshots_dir": str(tmp_path)}
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock()
    mock_page.context.new_cdp_session = AsyncMock(side_effect=RuntimeError("no CDP"))

    path = await browser_window.save_screenshot(
        mock_page, job_id=3, step="03-filled", config=config
    )

    mock_page.screenshot.assert_awaited_once_with(path=path, full_page=True)


# ── hide_window / show_window ──────────────────────────────────────────────


async def test_hide_window_minimizes_via_cdp():
    mock_page = MagicMock()
    mock_cdp = AsyncMock()
    mock_cdp.send = AsyncMock(side_effect=[{"windowId": 7}, None])
    mock_page.context.new_cdp_session = AsyncMock(return_value=mock_cdp)

    await browser_window.hide_window(mock_page)

    mock_cdp.send.assert_any_call("Browser.getWindowForTarget")
    mock_cdp.send.assert_any_call(
        "Browser.setWindowBounds",
        {"windowId": 7, "bounds": {"windowState": "minimized"}},
    )


async def test_show_window_restores_via_cdp():
    mock_page = MagicMock()
    mock_cdp = AsyncMock()
    mock_cdp.send = AsyncMock(side_effect=[{"windowId": 3}, None])
    mock_page.context.new_cdp_session = AsyncMock(return_value=mock_cdp)

    await browser_window.show_window(mock_page)

    mock_cdp.send.assert_any_call("Browser.getWindowForTarget")
    mock_cdp.send.assert_any_call(
        "Browser.setWindowBounds",
        {"windowId": 3, "bounds": {"windowState": "normal"}},
    )
