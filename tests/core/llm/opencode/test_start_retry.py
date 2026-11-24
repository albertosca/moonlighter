"""A run that dies before opencode's server is up never reached the provider: it is retried."""

from unittest.mock import patch

import pytest

from moonlighter.core.llm import opencode
from moonlighter.core.llm.opencode import call_opencode
from moonlighter.core.llm.opencode_events import parse_events
from tests.core.llm.opencode.events import NOT_STARTED_RUN, TEXT_RUN, error_event, output
from tests.core.llm.opencode.fake_opencode import FakeOpencode

SPAWN = "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec"


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(opencode, "_START_RETRY_DELAY_SECONDS", 0)


async def _call(fake: FakeOpencode) -> str:
    with patch(SPAWN, fake.create):
        return await call_opencode("Reply PONG.", "fake/echo")


def test_an_empty_session_id_is_no_session():
    assert parse_events(NOT_STARTED_RUN).session_id is None


async def test_a_run_that_never_started_is_retried_until_it_answers():
    fake = FakeOpencode(TEXT_RUN, failed_starts=[NOT_STARTED_RUN, NOT_STARTED_RUN])
    assert await _call(fake) == "PONG"
    assert len(fake.runs) == 3
    assert len(fake.deletes) == 1


async def test_a_run_that_never_starts_gives_up_after_two_retries():
    fake = FakeOpencode(NOT_STARTED_RUN, code=1)
    with pytest.raises(RuntimeError, match="before reporting readiness"):
        await _call(fake)
    assert len(fake.runs) == 3
    assert fake.deletes == []


async def test_an_error_after_the_start_is_never_retried():
    """The prompt may already have reached the provider: a retry would send it twice."""
    run = output(error_event({"message": "Standalone server exited before reporting readiness"}))
    fake = FakeOpencode(run, code=1)
    with pytest.raises(RuntimeError, match="before reporting readiness"):
        await _call(fake)
    assert len(fake.runs) == 1
