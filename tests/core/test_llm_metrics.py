"""Task 4: the LLM callers record into whatever operation_metrics scope is
active — CLI records time only (no token usage exposed), API records real
message.usage tokens."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

from anthropic.types import TextBlock
from gauntler.core.llm import _call_cli, make_api_caller
from gauntler.core.metrics import operation_metrics


async def test_cli_caller_records_a_call():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))

    with (
        patch("gauntler.core.llm.shutil.which", return_value="/usr/local/bin/claude"),
        patch("gauntler.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc),
        operation_metrics("op") as m,
    ):
        out = await _call_cli("hi", "model")

    assert out == "ok"
    assert m.calls == 1
    assert m.total_seconds >= 0.0
    assert m.input_tokens == 0  # CLI exposes no usage
    assert m.output_tokens == 0


async def test_cli_caller_records_even_on_failure():
    """Time in `finally`: a failed call still counts."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"boom"))

    with (
        patch("gauntler.core.llm.shutil.which", return_value="/usr/local/bin/claude"),
        patch("gauntler.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc),
        operation_metrics("op") as m,
        contextlib.suppress(RuntimeError),
    ):
        await _call_cli("hi", "model")

    assert m.calls == 1


async def test_api_caller_records_usage():
    mock_message = MagicMock()
    mock_message.usage = MagicMock(input_tokens=11, output_tokens=22)
    mock_message.content = [MagicMock(spec=TextBlock, text="hello")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("gauntler.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        with operation_metrics("op") as m:
            out = await caller("hi", "model")

    assert out == "hello"
    assert m.calls == 1
    assert m.input_tokens == 11
    assert m.output_tokens == 22


async def test_api_caller_records_even_on_failure():
    """Time in `finally`: a failed call still counts calls, with 0 tokens
    (usage was never assigned before the exception)."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=RuntimeError("boom"))

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("gauntler.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        with operation_metrics("op") as m, contextlib.suppress(RuntimeError):
            await caller("hi", "model")

    assert m.calls == 1
    assert m.input_tokens == 0
    assert m.output_tokens == 0
