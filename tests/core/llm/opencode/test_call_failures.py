"""A call that fails: refused before it starts, refused by its output, or cut short."""

import logging
import signal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from moonlighter.core.llm import opencode
from moonlighter.core.llm.opencode import call_opencode
from moonlighter.core.llm.spend_limit import is_spend_limit
from moonlighter.core.metrics import operation_metrics
from tests.core.llm.opencode.events import (
    BLOCKED_TOOL_RUN,
    FREE_LIMIT_RUN,
    TEXT_RUN,
    output,
    text_event,
    tool_event,
)
from tests.core.llm.opencode.fake_opencode import HANG, FakeOpencode

SPAWN = "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec"
KILLPG = "moonlighter.core.llm.isolation.os.killpg"


async def _call(fake: FakeOpencode, **keywords) -> str:
    with patch(SPAWN, fake.create):
        return await call_opencode("Reply PONG.", "fake/echo", **keywords)


@pytest.mark.parametrize("model", ["", "gpt-5", "/echo", "fake/", " / "])
async def test_a_model_without_a_provider_is_refused_before_anything_starts(model, tmp_path):
    spawn = AsyncMock()
    with (
        patch(SPAWN, spawn),
        operation_metrics("pin") as metrics,
        pytest.raises(RuntimeError, match="provider/model"),
    ):
        await call_opencode("prompt", model)
    spawn.assert_not_called()
    assert metrics.calls == 0
    assert not (tmp_path / "home").exists()


async def test_a_missing_binary_says_where_to_get_it(monkeypatch, tmp_path):
    monkeypatch.setattr(opencode.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match=r"https://opencode\.ai"):
        await call_opencode("prompt", "fake/echo")
    assert not (tmp_path / "home").exists()


async def test_the_free_limit_is_reported_as_a_usage_limit():
    with pytest.raises(RuntimeError, match="usage limit: Free usage limit reached") as caught:
        await _call(FakeOpencode(FREE_LIMIT_RUN, code=1))
    assert is_spend_limit(caught.value)


async def test_an_error_event_fails_the_call_even_with_a_zero_exit():
    run = output(text_event("half an answer"), {"type": "error", "error": {"message": "bad key"}})
    with pytest.raises(RuntimeError, match="opencode CLI failed: bad key"):
        await _call(FakeOpencode(run))


async def test_a_blocked_tool_call_discards_the_answer():
    run = BLOCKED_TOOL_RUN + TEXT_RUN
    with pytest.raises(RuntimeError, match=r"called a tool \(shell\)"):
        await _call(FakeOpencode(run))


async def test_a_tool_that_really_ran_discards_the_answer_too():
    run = output(tool_event("read", status="completed")) + TEXT_RUN
    with pytest.raises(RuntimeError, match=r"called a tool \(read\)"):
        await _call(FakeOpencode(run))


async def test_a_nonzero_exit_without_events_carries_stderr():
    with pytest.raises(RuntimeError, match="exited with code 1: no such model"):
        await _call(FakeOpencode(b"", code=1, stderr=b"no such model\n"))


async def test_a_blank_answer_is_an_error():
    with pytest.raises(RuntimeError, match="empty answer"):
        await _call(FakeOpencode(output(text_event("  \n"))))


async def test_the_session_is_deleted_when_the_call_fails():
    fake = FakeOpencode(BLOCKED_TOOL_RUN)
    with pytest.raises(RuntimeError):
        await _call(fake)
    assert len(fake.deletes) == 1


async def test_no_delete_runs_without_a_session_id():
    fake = FakeOpencode(b"", code=1, stderr=b"boom")
    with pytest.raises(RuntimeError):
        await _call(fake)
    assert fake.deletes == []


async def test_a_delete_that_exits_nonzero_is_logged_and_the_answer_survives(caplog):
    fake = FakeOpencode(TEXT_RUN, delete_code=1)
    with caplog.at_level(logging.WARNING):
        assert await _call(fake) == "PONG"
    assert any("session delete exited 1" in message for message in caplog.messages)


@pytest.mark.parametrize("failure", [OSError("no such file"), RuntimeError("weird")])
async def test_a_delete_that_raises_is_logged_and_the_answer_survives(failure, caplog):
    fake = FakeOpencode(TEXT_RUN, delete_failure=failure)
    with caplog.at_level(logging.ERROR):
        assert await _call(fake) == "PONG"
    assert "opencode session cleanup failed" in caplog.messages


async def test_a_delete_that_hangs_is_killed_and_the_answer_survives(monkeypatch, caplog):
    monkeypatch.setattr(opencode, "_SESSION_DELETE_TIMEOUT_SECONDS", 0.01)
    fake = FakeOpencode(TEXT_RUN, delete_failure=HANG)
    with patch(KILLPG) as killpg, caplog.at_level(logging.ERROR):
        assert await _call(fake) == "PONG"
    killpg.assert_called_once_with(4242, signal.SIGKILL)
    assert "opencode session cleanup failed" in caplog.messages


async def test_a_run_that_hangs_is_killed_with_its_group_and_leaves_no_workdir():
    fake = FakeOpencode(HANG)
    with (
        patch(KILLPG) as killpg,
        pytest.raises(RuntimeError, match=r"opencode CLI did not answer within 0\.01 s"),
    ):
        await _call(fake, timeout_seconds=0.01)
    killpg.assert_called_once_with(4242, signal.SIGKILL)
    assert not Path(fake.run.options["cwd"]).exists()  # noqa: ASYNC240 - a test inspecting the workdir; nothing else runs on the loop
    assert fake.deletes == []


async def test_a_failed_call_still_records_one_call():
    with operation_metrics("pin") as metrics, pytest.raises(RuntimeError):
        await _call(FakeOpencode(b"", code=1))
    assert metrics.calls == 1
