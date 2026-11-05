from unittest.mock import MagicMock, patch

import pytest

from moonlighter.core.llm.cursor import call_cursor
from tests.core.llm.fake_processes import cursor_process


async def test_call_cursor_empty_prompt_still_calls_subprocess():
    mock_process = cursor_process(b"response")

    with patch(
        "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
    ):
        result = await call_cursor("", "model")

    assert result == "response"
    assert mock_process.communicate.call_args.kwargs["input"] == b""


async def test_cursor_caller_satisfies_llm_caller_contract():
    mock_process = cursor_process(b"result")

    with patch(
        "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
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
        "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
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
        "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
    ):
        await call_cursor("PROMPT_ONLY", "m")
    assert captured["input"] == b"PROMPT_ONLY"


@pytest.mark.parametrize(
    ("stdout", "stderr", "code"),
    [(b"", b"bad \xff byte", 1), (b"bad \xff byte", b"", 0)],
    ids=["error-output", "answer"],
)
async def test_call_cursor_decodes_its_output_strictly(stdout, stderr, code):
    """Same pin as the claude CLI's: a byte that is not UTF-8 raises
    UnicodeDecodeError, not the RuntimeError a caller expects.
    """
    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec",
            return_value=cursor_process(stdout, stderr, code),
        ),
        pytest.raises(UnicodeDecodeError),
    ):
        await call_cursor("prompt", "model")
