"""call_cursor records one call, a non-negative total_seconds and zero tokens in the active
operation_metrics scope, still counts the call when it fails or when forget_cursor_call
raises, and counts none when `agent` is missing.
"""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moonlighter.core.llm.cursor import call_cursor
from moonlighter.core.metrics import operation_metrics
from tests.core.llm.fake_processes import cursor_process


async def test_cursor_caller_records_a_call():
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"ok", b""))

    with (
        patch("moonlighter.core.llm.cursor.shutil.which", return_value="/usr/local/bin/agent"),
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ),
        operation_metrics("op") as metrics,
    ):
        out = await call_cursor("hi", "model")

    assert out == "ok"
    assert metrics.calls == 1
    assert metrics.total_seconds >= 0.0
    assert metrics.input_tokens == 0
    assert metrics.output_tokens == 0


async def test_cursor_caller_records_even_on_failure():
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"boom"))

    with (
        patch("moonlighter.core.llm.cursor.shutil.which", return_value="/usr/local/bin/agent"),
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ),
        operation_metrics("op") as metrics,
        contextlib.suppress(RuntimeError),
    ):
        await call_cursor("hi", "model")

    assert metrics.calls == 1


async def test_call_cursor_records_no_call_when_agent_is_missing():
    with (
        patch("moonlighter.core.llm.cursor.shutil.which", return_value=None),
        operation_metrics("pin") as metrics,
        pytest.raises(RuntimeError),
    ):
        await call_cursor("prompt", "model")
    assert metrics.calls == 0


async def test_call_cursor_records_its_call_even_when_cleanup_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec",
            return_value=cursor_process(),
        ),
        patch(
            "moonlighter.core.llm.cursor.forget_cursor_call", side_effect=RuntimeError("cleanup")
        ),
        operation_metrics("pin") as metrics,
        pytest.raises(RuntimeError, match=r"^cleanup$"),
    ):
        await call_cursor("prompt", "model")
    assert metrics.calls == 1
