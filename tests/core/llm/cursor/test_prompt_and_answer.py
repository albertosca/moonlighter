from unittest.mock import MagicMock, patch

import pytest

from moonlighter.core.llm.cursor import call_cursor
from tests.core.llm.fake_processes import cursor_process


async def test_call_cursor_empty_prompt_still_calls_subprocess():
    mock_process = cursor_process(b"response")

    with patch(
        "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec", return_value=mock_process
    ):
        result = await call_cursor("", "model")

    assert result == "response"
    assert mock_process.communicate.call_args.kwargs["input"] == b""


async def test_cursor_caller_satisfies_llm_caller_contract():
    mock_process = cursor_process(b"result")

    with patch(
        "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec", return_value=mock_process
    ):
        result = await call_cursor("hello", "any-model")

    assert isinstance(result, str)


async def test_cursor_concatenates_cache_prefix():
    captured: dict[str, object] = {}

    async def fake_communicate(
        *positional_arguments: object, **keyword_arguments: object
    ) -> tuple[bytes, bytes]:
        captured["input"] = keyword_arguments["input"]
        return (b"ok", b"")

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = fake_communicate

    with patch(
        "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec", return_value=mock_process
    ):
        await call_cursor("DYN", "m", cache_prefix="STATIC")
    assert captured["input"] == b"STATIC\n\nDYN"


async def test_cursor_no_cache_prefix_keeps_prompt_unchanged():
    captured: dict[str, object] = {}

    async def fake_communicate(
        *positional_arguments: object, **keyword_arguments: object
    ) -> tuple[bytes, bytes]:
        captured["input"] = keyword_arguments["input"]
        return (b"ok", b"")

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = fake_communicate

    with patch(
        "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec", return_value=mock_process
    ):
        await call_cursor("PROMPT_ONLY", "m")
    assert captured["input"] == b"PROMPT_ONLY"


async def test_call_cursor_replaces_bad_bytes_in_its_error_output():
    """A non-UTF-8 byte in stderr must not hide the CLI's own error behind a UnicodeDecodeError."""
    with (
        patch(
            "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec",
            return_value=cursor_process(b"", b"bad \xff byte", 1),
        ),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_cursor("prompt", "model")
    assert str(raised.value) == "agent CLI exited with code 1: bad \ufffd byte"


async def test_call_cursor_refuses_an_answer_that_is_not_utf8():
    """A corrupted answer is an error the caller expects, never half-used text."""
    with (
        patch(
            "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec",
            return_value=cursor_process(b"bad \xff byte", b"", 0),
        ),
        pytest.raises(RuntimeError, match=r"^agent CLI answered with bytes that are not UTF-8"),
    ):
        await call_cursor("prompt", "model")
