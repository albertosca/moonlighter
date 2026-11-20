from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moonlighter.core.llm.claude_cli import call_cli


async def test_call_cli_empty_prompt_still_calls_subprocess():
    """Empty prompt is passed as-is, via stdin."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"response", b""))

    with patch(
        "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec", return_value=mock_process
    ):
        result = await call_cli("", "model")

    assert result == "response"
    assert mock_process.communicate.call_args.kwargs["input"] == b""


async def test_cli_caller_satisfies_llm_caller_contract():
    """call_cli satisfies (prompt: str, model: str) -> str contract."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"result", b""))

    with patch(
        "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec", return_value=mock_process
    ):
        result = await call_cli("hello", "any-model")

    assert isinstance(result, str)


async def test_cli_concatenates_cache_prefix():
    """cache_prefix is concatenated to the prompt in the cli backend."""
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
        await call_cli("DYN", "m", cache_prefix="STATIC")
    assert captured["input"] == b"STATIC\n\nDYN"


async def test_cli_no_cache_prefix_keeps_prompt_unchanged():
    """cache_prefix=None (default) keeps the original behavior in the cli."""
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
        await call_cli("PROMPT_ONLY", "m")
    assert captured["input"] == b"PROMPT_ONLY"


async def test_call_cli_replaces_bad_bytes_in_its_error_output():
    """A non-UTF-8 byte in stderr must not hide the CLI's own error behind a UnicodeDecodeError."""
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"bad \xff byte"))
    with (
        patch(
            "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_cli("prompt", "model")
    assert str(raised.value) == "claude CLI exited with code 1: bad \ufffd byte"


async def test_call_cli_refuses_an_answer_that_is_not_utf8():
    """A corrupted answer is an error the caller expects, never half-used text."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"bad \xff byte", b""))
    with (
        patch(
            "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        pytest.raises(RuntimeError, match=r"^claude CLI answered with bytes that are not UTF-8"),
    ):
        await call_cli("prompt", "model")
