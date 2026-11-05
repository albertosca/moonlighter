"""_launch_browser asks for an OS-chosen debug port, deletes a stale port file first, and kills a browser that never comes up."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.core import browser

from tests.core.browser_config import CONFIG


async def test_launch_browser_uses_random_port_flag(tmp_path):
    mock_process = MagicMock()
    mock_process.kill = MagicMock()
    with (
        patch("moonlighter.core.browser.subprocess.Popen", return_value=mock_process) as popen,
        patch("moonlighter.core.browser._read_devtools_port", side_effect=[None, 9333]),
        patch("moonlighter.core.browser._devtools_ready", return_value=True),
    ):
        port = await browser._launch_browser(CONFIG, tmp_path)
    assert port == 9333
    launch_arguments = popen.call_args.args[0]
    assert "--remote-debugging-port=0" in launch_arguments
    assert not any(
        argument.startswith("--remote-debugging-port=9222") for argument in launch_arguments
    )


async def test_launch_browser_deletes_stale_port_file_before_launch(tmp_path):
    """A leftover DevToolsActivePort from a dead session must never be trusted —
    it's deleted before the new process starts, so a crashed launch can't
    silently reconnect to a stale/foreign port (S-03)."""
    stale = tmp_path / "DevToolsActivePort"
    stale.write_text("11111\n/devtools/browser/stale\n")
    mock_process = MagicMock()
    mock_process.kill = MagicMock()

    with (
        patch("moonlighter.core.browser.subprocess.Popen", return_value=mock_process),
        patch("moonlighter.core.browser._read_devtools_port", return_value=None),
        patch("moonlighter.core.browser.asyncio.sleep", new=AsyncMock()),
        pytest.raises(RuntimeError),
    ):
        await browser._launch_browser(CONFIG, tmp_path)

    assert not stale.exists()


async def test_launch_browser_raises_when_port_never_appears(tmp_path):
    mock_process = MagicMock()
    mock_process.kill = MagicMock()
    with (
        patch("moonlighter.core.browser.subprocess.Popen", return_value=mock_process),
        patch("moonlighter.core.browser._read_devtools_port", return_value=None),
        patch("moonlighter.core.browser.asyncio.sleep", new=AsyncMock()),
        pytest.raises(RuntimeError, match="Browser"),
    ):
        await browser._launch_browser(CONFIG, tmp_path)
    mock_process.kill.assert_called_once()
