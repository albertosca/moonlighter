from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.core.llm.claude_cli import call_cli


async def test_call_cli_empty_prompt_still_calls_subprocess():
    """Empty prompt is passed as-is, via stdin."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"response", b""))

    with patch(
        "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec", return_value=mock_process
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
        "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec", return_value=mock_process
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
        "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec", return_value=mock_process
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
        "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec", return_value=mock_process
    ):
        await call_cli("PROMPT_ONLY", "m")
    assert captured["input"] == b"PROMPT_ONLY"


@pytest.mark.parametrize(
    ("stdout", "stderr", "code"),
    [(b"", b"bad \xff byte", 1), (b"bad \xff byte", b"", 0)],
    ids=["error-output", "answer"],
)
async def test_call_cli_decodes_its_output_strictly(stdout, stderr, code):
    """Today's behaviour, pinned so the split cannot change it: a byte that is not
    UTF-8 raises UnicodeDecodeError, not the RuntimeError a caller expects.
    """
    mock_process = MagicMock()
    mock_process.returncode = code
    mock_process.communicate = AsyncMock(return_value=(stdout, stderr))
    with (
        patch(
            "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        pytest.raises(UnicodeDecodeError),
    ):
        await call_cli("prompt", "model")
