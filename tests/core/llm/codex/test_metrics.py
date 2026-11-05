import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from moonlighter.core.llm import codex
from moonlighter.core.llm.codex import call_codex
from moonlighter.core.metrics import operation_metrics
from tests.core.llm.codex.fake_codex import LOGGED_IN, fake_codex, fake_process


async def test_a_codex_call_that_answers_records_one_call():
    create, _, _ = fake_codex("ok")
    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        operation_metrics("pin") as metrics,
    ):
        await call_codex("prompt", "gpt-5")
    assert metrics.calls == 1


async def test_a_codex_call_that_exits_nonzero_records_one_call():
    launch = AsyncMock(side_effect=[fake_process(LOGGED_IN), fake_process(b"", b"boom", 2)])
    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", launch),
        operation_metrics("pin") as metrics,
        pytest.raises(RuntimeError),
    ):
        await call_codex("prompt", "gpt-5")
    assert metrics.calls == 1


def test_a_refused_model_records_no_call_and_creates_no_workdir(tmp_path):
    with operation_metrics("pin") as metrics, pytest.raises(RuntimeError):
        asyncio.run(call_codex("prompt", "claude-sonnet-4-6"))
    assert metrics.calls == 0
    assert not (tmp_path / "home").exists()


def test_a_missing_codex_binary_records_no_call_and_creates_no_workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(codex.shutil, "which", lambda name: None)
    with operation_metrics("pin") as metrics, pytest.raises(RuntimeError):
        asyncio.run(call_codex("prompt", "gpt-5"))
    assert metrics.calls == 0
    assert not (tmp_path / "home").exists()


async def test_a_cleanup_that_raises_still_records_the_call():
    create, _, _ = fake_codex("ok")
    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        patch("moonlighter.core.llm.codex.remove_quietly", side_effect=RuntimeError("cleanup")),
        operation_metrics("pin") as metrics,
        pytest.raises(RuntimeError, match=r"^cleanup$"),
    ):
        await call_codex("prompt", "gpt-5")
    assert metrics.calls == 1
