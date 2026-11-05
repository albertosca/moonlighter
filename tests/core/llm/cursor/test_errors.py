import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moonlighter.core.llm.cursor import call_cursor
from tests.core.llm.fake_processes import cursor_process


async def test_call_cursor_raises_on_nonzero_exit():
    mock_process = cursor_process(b"", b"some error message", code=1)

    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_cursor("prompt", "model")

    assert "code 1" in str(raised.value)
    assert "some error message" in str(raised.value)


async def test_call_cursor_stderr_truncated_to_300_chars():
    mock_process = cursor_process(b"", b"E" * 500, code=2)

    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_cursor("p", "m")

    error_message = str(raised.value)
    assert "E" * 300 in error_message
    assert "E" * 301 not in error_message


async def test_call_cursor_uses_stdout_when_stderr_is_empty():
    mock_process = cursor_process(b"stdout detail", b"", code=1)

    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ),
        pytest.raises(RuntimeError, match="stdout detail"),
    ):
        await call_cursor("prompt", "model")


async def test_call_cursor_errors_clearly_when_no_binary_is_on_path():
    with (
        patch("moonlighter.core.llm.cursor.shutil.which", return_value=None),
        pytest.raises(RuntimeError, match="agent login"),
    ):
        await call_cursor("the prompt", "model")


@pytest.mark.parametrize("group_already_gone", [False, True])
async def test_call_cursor_kills_a_subprocess_that_does_not_answer_in_time(group_already_gone):
    """Same rule as the claude CLI: a hung agent is killed with its process
    group, and a group that already exited is not an error.
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
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec,
        patch("moonlighter.core.llm.isolation.os.killpg", killpg),
        pytest.raises(RuntimeError, match=r"agent CLI did not answer within 0\.05 s"),
    ):
        await call_cursor("prompt", "model", timeout_seconds=0.05)
    killpg.assert_called_once_with(4242, signal.SIGKILL)
    mock_process.wait.assert_awaited_once()
    assert mock_exec.call_args.kwargs["start_new_session"] is True


async def test_cursor_cleanup_failure_does_not_replace_the_result(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    mock_process = cursor_process(b"the answer")
    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ),
        patch("moonlighter.core.llm.isolation.shutil.rmtree", side_effect=OSError("busy")),
        caplog.at_level("ERROR"),
    ):
        result = await call_cursor("prompt", "model")
    assert result == "the answer"
    assert "cursor cleanup failed" in caplog.text


async def test_cursor_cleanup_failure_does_not_hide_a_usage_limit(tmp_path, monkeypatch):
    mock_process = cursor_process()
    mock_process.communicate = AsyncMock(side_effect=RuntimeError("usage limit reached"))
    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ),
        patch("moonlighter.core.llm.isolation.shutil.rmtree", side_effect=OSError("busy")),
        pytest.raises(RuntimeError, match="usage limit"),
    ):
        await call_cursor("prompt", "model")


async def test_call_cursor_missing_binary_message_is_pinned_word_for_word():
    with (
        patch("moonlighter.core.llm.cursor.shutil.which", return_value=None),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_cursor("the prompt", "model")
    assert str(raised.value) == (
        "the `agent` CLI was not found on PATH (also looked for `cursor-agent`). "
        "Install the Cursor CLI and run `agent login`."
    )


async def test_call_cursor_timeout_message_is_pinned_word_for_word():
    mock_process = cursor_process()
    mock_process.pid = 4242
    mock_process.communicate = AsyncMock(side_effect=TimeoutError)
    mock_process.wait = AsyncMock(return_value=-9)
    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ),
        patch("moonlighter.core.llm.isolation.os.killpg") as killpg,
        pytest.raises(RuntimeError) as raised,
    ):
        await call_cursor("prompt", "model", timeout_seconds=7)
    assert str(raised.value) == (
        "agent CLI did not answer within 7 s — killed "
        "(raise llm_timeout_seconds in config.yaml if your calls are legitimately slow)"
    )
    killpg.assert_called_once_with(4242, signal.SIGKILL)


@pytest.mark.parametrize(
    ("stdout", "stderr", "message"),
    [
        (b"", b"some error message\n", "agent CLI exited with code 1: some error message"),
        (b"from stdout\n", b"", "agent CLI exited with code 1: from stdout"),
        (b"from stdout", b"  \n", "agent CLI exited with code 1: from stdout"),
    ],
    ids=["stderr", "stdout-fallback", "whitespace-stderr-falls-back"],
)
async def test_call_cursor_exit_message_is_pinned_word_for_word(stdout, stderr, message):
    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec",
            return_value=cursor_process(stdout, stderr, code=1),
        ),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_cursor("prompt", "model")
    assert str(raised.value) == message
