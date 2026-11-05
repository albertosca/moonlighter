import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moonlighter.core.llm.claude_cli import call_cli


@pytest.mark.parametrize("group_already_gone", [False, True])
async def test_call_cli_kills_a_subprocess_that_does_not_answer_in_time(group_already_gone):
    """One `claude -p` call hung for the whole 300 s on a 1,351-character page
    (llm-tests-forge run, 2026-09-25): nothing ended it but the harness. The
    whole process group is killed (see tests/core/llm/test_isolation.py for the real
    processes), and a group that exited in the meantime is not an error.
    """

    async def never_answers(input=None):  # noqa: A002 - mirrors Process.communicate(input=...)
        await asyncio.sleep(3600)

    mock_process = MagicMock()
    mock_process.pid = 4242
    mock_process.communicate = never_answers
    mock_process.wait = AsyncMock(return_value=-9)
    killpg = MagicMock(side_effect=ProcessLookupError if group_already_gone else None)
    with (
        patch(
            "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        patch("moonlighter.core.llm.isolation.os.killpg", killpg),
        pytest.raises(RuntimeError, match=r"did not answer within 0\.05 s"),
    ):
        await call_cli("prompt", "model", timeout_seconds=0.05)
    killpg.assert_called_once_with(4242, signal.SIGKILL)
    mock_process.wait.assert_awaited_once()


async def test_call_cli_raises_on_nonzero_exit():
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"some error message"))

    with (
        patch(
            "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_cli("prompt", "model")

    assert "code 1" in str(raised.value)
    assert "some error message" in str(raised.value)


async def test_call_cli_stderr_truncated_to_300_chars():
    """Long stderr is truncated at 300 chars in the error message."""
    long_stderr = b"E" * 500
    mock_process = MagicMock()
    mock_process.returncode = 2
    mock_process.communicate = AsyncMock(return_value=(b"", long_stderr))

    with (
        patch(
            "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_cli("p", "m")

    error_message = str(raised.value)
    assert "E" * 300 in error_message
    assert "E" * 301 not in error_message


async def test_call_cli_errors_clearly_when_claude_is_not_on_path():
    with (
        patch("moonlighter.core.llm.claude_cli.shutil.which", return_value=None),
        pytest.raises(RuntimeError, match="claude"),
    ):
        await call_cli("the prompt", "model")


async def test_call_cli_missing_binary_message_is_pinned_word_for_word():
    with (
        patch("moonlighter.core.llm.claude_cli.shutil.which", return_value=None),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_cli("the prompt", "model")
    assert str(raised.value) == (
        "the `claude` CLI was not found on PATH. Install it, or put it on PATH — "
        "this project uses the CLI backend (the claude.ai subscription), not an API key."
    )


async def test_call_cli_timeout_message_is_pinned_word_for_word():
    mock_process = MagicMock()
    mock_process.pid = 4242
    mock_process.communicate = AsyncMock(side_effect=TimeoutError)
    mock_process.wait = AsyncMock(return_value=-9)
    with (
        patch(
            "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        patch("moonlighter.core.llm.isolation.os.killpg") as killpg,
        pytest.raises(RuntimeError) as raised,
    ):
        await call_cli("prompt", "model", timeout_seconds=7)
    assert str(raised.value) == (
        "claude CLI did not answer within 7 s — killed "
        "(raise llm_timeout_seconds in config.yaml if your calls are legitimately slow)"
    )
    killpg.assert_called_once_with(4242, signal.SIGKILL)


@pytest.mark.parametrize(
    ("stdout", "stderr", "message"),
    [
        (b"", b"some error message\n", "claude CLI exited with code 1: some error message"),
        (b"from stdout\n", b"", "claude CLI exited with code 1: from stdout"),
        (b"from stdout", b"  \n", "claude CLI exited with code 1: from stdout"),
    ],
    ids=["stderr", "stdout-fallback", "whitespace-stderr-falls-back"],
)
async def test_call_cli_exit_message_is_pinned_word_for_word(stdout, stderr, message):
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(stdout, stderr))
    with (
        patch(
            "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_cli("prompt", "model")
    assert str(raised.value) == message
