"""Program C (2026-08-18): opt-in mark-read+archive after the sync applies an update.

Two layers: archive_ref_matched (certainty only) and archive_all_classified (superset).
'unrelated' mail is NEVER touched — the tracked mailbox can hold personal mail.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.core.db import init_db
from moonlighter.tracking.sync.monitor import sync_responses

from tests.tracking.archive_settings import archive_config
from tests.tracking.llm_callers import make_llm_caller
from tests.tracking.pipeline_rows import make_application, make_job


def _service():
    return MagicMock()


async def _run(config, message, classification, *, message_id="msgA"):
    with (
        patch(
            "moonlighter.tracking.sync.monitor.setup_gmail_service",
            return_value=_service(),
        ),
        patch(
            "moonlighter.tracking.sync.monitor.fetch_recent_messages",
            return_value=[{"id": message_id, "threadId": "t"}],
        ),
        patch("moonlighter.tracking.sync.monitor.parse_message", return_value=message),
        patch(
            "moonlighter.tracking.sync.monitor.classify_response",
            new=AsyncMock(return_value=classification),
        ),
        patch("moonlighter.tracking.sync.monitor.archive_message") as mock_archive,
        patch("moonlighter.tracking.sync.monitor.mark_processed"),
        patch("moonlighter.tracking.sync.monitor.get_or_create_label", return_value="Label_p"),
    ):
        updates = await sync_responses(config, make_llm_caller(classification))
    return updates, mock_archive


@pytest.mark.asyncio
async def test_ref_matched_archives_when_layer_one_is_on(temporary_database):
    init_db()
    job = make_job(temporary_database)
    make_application(job, status="submitted", email_ref="cflag1")
    message = {
        "to": "candidaturas+cflag1@gmail.com",
        "from_": "hr@x.com",
        "subject": "s",
        "body": "b",
    }
    classification = {
        "type": "rejection",
        "stage": None,
        "new_stage": None,
        "company": None,
        "job_title": None,
        "summary": "r",
    }
    _, mock_archive = await _run(archive_config(archive_ref_matched=True), message, classification)
    mock_archive.assert_called_once()
    assert mock_archive.call_args[0][1] == "msgA"


@pytest.mark.asyncio
async def test_uncertain_stays_in_inbox_with_only_layer_one(temporary_database):
    init_db()
    message = {"to": "candidaturas@gmail.com", "from_": "hr@x.com", "subject": "s", "body": "b"}
    classification = {
        "type": "rejection",
        "stage": None,
        "new_stage": None,
        "company": "Nowhere",
        "job_title": "Ghost",
        "summary": "r",
    }
    _, mock_archive = await _run(archive_config(archive_ref_matched=True), message, classification)
    mock_archive.assert_not_called()


@pytest.mark.asyncio
async def test_layer_two_archives_uncertain_too(temporary_database):
    init_db()
    message = {"to": "candidaturas@gmail.com", "from_": "hr@x.com", "subject": "s", "body": "b"}
    classification = {
        "type": "rejection",
        "stage": None,
        "new_stage": None,
        "company": "Nowhere",
        "job_title": "Ghost",
        "summary": "r",
    }
    _, mock_archive = await _run(
        archive_config(archive_all_classified=True), message, classification
    )
    mock_archive.assert_called_once()


@pytest.mark.asyncio
async def test_unrelated_mail_is_never_archived(temporary_database):
    init_db()
    message = {
        "to": "candidaturas@gmail.com",
        "from_": "mom@x.com",
        "subject": "s",
        "body": "b",
    }
    classification = {"type": "unrelated", "summary": ""}
    _, mock_archive = await _run(
        archive_config(archive_ref_matched=True, archive_all_classified=True),
        message,
        classification,
    )
    mock_archive.assert_not_called()


@pytest.mark.asyncio
async def test_flags_off_means_zero_archive_calls(temporary_database):
    init_db()
    job = make_job(temporary_database)
    make_application(job, status="submitted", email_ref="cflag2")
    message = {
        "to": "candidaturas+cflag2@gmail.com",
        "from_": "hr@x.com",
        "subject": "s",
        "body": "b",
    }
    classification = {
        "type": "rejection",
        "stage": None,
        "new_stage": None,
        "company": None,
        "job_title": None,
        "summary": "r",
    }
    _, mock_archive = await _run(archive_config(), message, classification)
    mock_archive.assert_not_called()


@pytest.mark.asyncio
async def test_an_archive_failure_does_not_break_the_sync(temporary_database):
    init_db()
    job = make_job(temporary_database)
    make_application(job, status="submitted", email_ref="cflag3")
    message = {
        "to": "candidaturas+cflag3@gmail.com",
        "from_": "hr@x.com",
        "subject": "s",
        "body": "b",
    }
    classification = {
        "type": "rejection",
        "stage": None,
        "new_stage": None,
        "company": None,
        "job_title": None,
        "summary": "r",
    }
    with (
        patch(
            "moonlighter.tracking.sync.monitor.setup_gmail_service",
            return_value=MagicMock(),
        ),
        patch(
            "moonlighter.tracking.sync.monitor.fetch_recent_messages",
            return_value=[{"id": "msgF", "threadId": "t"}],
        ),
        patch("moonlighter.tracking.sync.monitor.parse_message", return_value=message),
        patch(
            "moonlighter.tracking.sync.monitor.classify_response",
            new=AsyncMock(return_value=classification),
        ),
        patch(
            "moonlighter.tracking.sync.monitor.archive_message",
            side_effect=RuntimeError("modify denied"),
        ),
        patch("moonlighter.tracking.sync.monitor.mark_processed"),
        patch("moonlighter.tracking.sync.monitor.get_or_create_label", return_value="Label_p"),
    ):
        updates = await sync_responses(
            archive_config(archive_ref_matched=True), make_llm_caller(classification)
        )
    assert len(updates) == 1  # the pipeline update survived the Gmail failure
