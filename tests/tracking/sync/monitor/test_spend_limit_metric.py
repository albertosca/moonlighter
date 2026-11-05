"""The sync records a spend-limit hit in the metrics, and only a spend-limit hit."""

from unittest.mock import MagicMock, patch

import pytest
from moonlighter.core.db import init_db
from moonlighter.tracking.sync.monitor import sync_responses

CONFIG = {"email": {"address": "candidaturas@gmail.com"}}
MESSAGE = {
    "to": "candidaturas+metric01@gmail.com",
    "from_": "hr@anthropic.com",
    "subject": "Technical interview",
    "body": "We would like to schedule an interview.",
}


async def _sync_with_failing_caller(failure: Exception) -> MagicMock:
    async def failing_caller(prompt, model, cache_prefix=None):
        raise failure

    with (
        patch("moonlighter.tracking.sync.monitor.setup_gmail_service", return_value=MagicMock()),
        patch(
            "moonlighter.tracking.sync.monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.sync.monitor.parse_message", return_value=MESSAGE),
        patch("moonlighter.tracking.sync.monitor.record_spend_limit_hit") as record_mock,
    ):
        await sync_responses(CONFIG, failing_caller)
    return record_mock


@pytest.mark.usefixtures("temporary_database")
async def test_a_spend_limit_hit_is_recorded_once():
    init_db()
    record_mock = await _sync_with_failing_caller(
        RuntimeError("rate limit exceeded, please retry later")
    )
    record_mock.assert_called_once_with()


@pytest.mark.usefixtures("temporary_database")
async def test_an_ordinary_classification_failure_records_no_spend_limit_hit():
    init_db()
    record_mock = await _sync_with_failing_caller(RuntimeError("transient LLM error"))
    record_mock.assert_not_called()
