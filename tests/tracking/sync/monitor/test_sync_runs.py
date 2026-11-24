"""A sync records its run only when it read the whole lookback window."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from moonlighter.core.config.loading import build_config
from moonlighter.core.db import EmailSyncRun, ProcessedEmail, init_db
from moonlighter.tracking.sync.monitor import sync_responses

CONFIG = {"email": {"address": "candidaturas@gmail.com"}}
MESSAGE = {
    "to": "candidaturas+run01@gmail.com",
    "from_": "hr@acme.com",
    "subject": "Hi",
    "body": "Hello",
}


async def _sync(caller):
    with (
        patch("moonlighter.tracking.sync.monitor.setup_gmail_service", return_value=MagicMock()),
        patch(
            "moonlighter.tracking.sync.monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.sync.monitor.parse_message", return_value=MESSAGE),
        patch("moonlighter.tracking.sync.monitor.record_spend_limit_hit"),
    ):
        await sync_responses(build_config(CONFIG), caller)


def _failing(message):
    async def caller(prompt, model, cache_prefix=None):
        raise RuntimeError(message)

    return caller


@pytest.mark.usefixtures("temporary_database")
async def test_a_sync_with_a_classification_failure_records_nothing():
    init_db()
    await _sync(_failing("transient LLM error"))
    assert EmailSyncRun.select().count() == 0


@pytest.mark.usefixtures("temporary_database")
async def test_a_sync_that_fetched_the_message_cap_records_nothing():
    init_db()
    ProcessedEmail.create(message_id="msg0")
    with patch("moonlighter.tracking.sync.sweep.MAXIMUM_MESSAGES_PER_SYNC", 1):
        await _sync(_failing("unused: msg0 was processed before"))
    assert EmailSyncRun.select().count() == 0


@pytest.mark.usefixtures("temporary_database")
async def test_a_complete_sync_records_the_start_of_the_window_it_read():
    init_db()
    with (
        patch("moonlighter.tracking.sync.monitor.setup_gmail_service", return_value=MagicMock()),
        patch("moonlighter.tracking.sync.monitor.fetch_recent_messages", return_value=[]),
    ):
        await sync_responses(
            build_config({"email": {"address": "candidaturas@gmail.com", "lookback_days": 20}}),
            _failing("unused"),
        )
    run = EmailSyncRun.get()
    assert timedelta(days=20) <= run.finished_at - run.window_start < timedelta(days=20, minutes=1)


@pytest.mark.usefixtures("temporary_database")
async def test_an_empty_window_is_still_a_complete_run():
    init_db()
    with (
        patch("moonlighter.tracking.sync.monitor.setup_gmail_service", return_value=MagicMock()),
        patch("moonlighter.tracking.sync.monitor.fetch_recent_messages", return_value=[]),
    ):
        await sync_responses(build_config(CONFIG), _failing("unused"))
    assert EmailSyncRun.select().count() == 1


@pytest.mark.usefixtures("temporary_database")
async def test_a_sync_cut_by_the_spend_limit_records_nothing():
    init_db()
    await _sync(_failing("rate limit exceeded, please retry later"))
    assert EmailSyncRun.select().count() == 0


@pytest.mark.usefixtures("temporary_database")
async def test_a_sync_that_raises_records_nothing():
    init_db()
    with (
        patch("moonlighter.tracking.sync.monitor.setup_gmail_service", return_value=MagicMock()),
        patch(
            "moonlighter.tracking.sync.monitor.fetch_recent_messages",
            side_effect=RuntimeError("gmail down"),
        ),
        pytest.raises(RuntimeError, match="gmail down"),
    ):
        await sync_responses(build_config(CONFIG), _failing("unused"))
    assert EmailSyncRun.select().count() == 0
