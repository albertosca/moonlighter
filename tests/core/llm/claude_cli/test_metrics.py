"""call_cli records one call, a non-negative total_seconds and zero tokens in the active
operation_metrics scope, still counts the call when it fails, and counts none when `claude`
is missing."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.core.llm.claude_cli import call_cli
from moonlighter.core.metrics import operation_metrics


async def test_cli_caller_records_a_call():
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"ok", b""))

    with (
        patch("moonlighter.core.llm.claude_cli.shutil.which", return_value="/usr/local/bin/claude"),
        patch(
            "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        operation_metrics("op") as metrics,
    ):
        out = await call_cli("hi", "model")

    assert out == "ok"
    assert metrics.calls == 1
    assert metrics.total_seconds >= 0.0
    assert metrics.input_tokens == 0  # CLI exposes no usage
    assert metrics.output_tokens == 0


async def test_cli_caller_records_even_on_failure():
    """Time in `finally`: a failed call still counts."""
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"boom"))

    with (
        patch("moonlighter.core.llm.claude_cli.shutil.which", return_value="/usr/local/bin/claude"),
        patch(
            "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        operation_metrics("op") as metrics,
        contextlib.suppress(RuntimeError),
    ):
        await call_cli("hi", "model")

    assert metrics.calls == 1


async def test_call_cli_records_no_call_when_claude_is_missing():
    with (
        patch("moonlighter.core.llm.claude_cli.shutil.which", return_value=None),
        operation_metrics("pin") as metrics,
        pytest.raises(RuntimeError),
    ):
        await call_cli("prompt", "model")
    assert metrics.calls == 0
