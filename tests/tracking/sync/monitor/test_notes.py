"""The notes a sync appends to an application, and its refreshed timestamp."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Application, init_db
from moonlighter.tracking.sync.monitor import sync_responses
from tests.tracking.llm_callers import make_llm_caller
from tests.tracking.pipeline_rows import make_application, make_job
from tests.tracking.sync_setup import SYNC_CONFIG


async def test_notes_include_date_and_match_type(temporary_database):
    init_db()
    job = make_job(temporary_database)
    application = make_application(job, status="submitted", email_ref="nt001", notes=None)

    classify_result = {
        "type": "interview",
        "stage": "technical_interview",
        "new_stage": None,
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "Technical interview scheduled for 05/06.",
    }
    message = {
        "to": "candidaturas+nt001@gmail.com",
        "from_": "hr@anthropic.com",
        "subject": "Interview",
        "body": "We would like to schedule.",
    }

    with (
        patch("moonlighter.tracking.sync.monitor.setup_gmail_service", return_value=MagicMock()),
        patch(
            "moonlighter.tracking.sync.monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.sync.monitor.parse_message", return_value=message),
        patch(
            "moonlighter.tracking.sync.monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.sync.monitor.mark_processed"),
        patch("moonlighter.tracking.sync.monitor.get_or_create_label", return_value="Label_proc"),
    ):
        await sync_responses(SYNC_CONFIG, make_llm_caller(classify_result))

    notes = Application.get_by_id(application.id).notes
    today = date.today().strftime("%Y-%m-%d")  # noqa: DTZ011 - the sync stamps notes with the local calendar day
    assert today in notes
    assert "interview" in notes
    assert "Technical interview scheduled" in notes
    assert "match: ref" in notes


async def test_notes_appended_to_existing_notes(temporary_database):
    init_db()
    job = make_job(temporary_database)
    existing_notes = "[2026-05-01] screening: Initial call. (match: fuzzy)"
    application = make_application(
        job, status="screening", email_ref="app001", notes=existing_notes
    )

    classify_result = {
        "type": "interview",
        "stage": "technical_interview",
        "new_stage": None,
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "Technical interview.",
    }
    message = {
        "to": "candidaturas+app001@gmail.com",
        "from_": "hr@anthropic.com",
        "subject": "Technical interview",
        "body": "Next step.",
    }

    with (
        patch("moonlighter.tracking.sync.monitor.setup_gmail_service", return_value=MagicMock()),
        patch(
            "moonlighter.tracking.sync.monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.sync.monitor.parse_message", return_value=message),
        patch(
            "moonlighter.tracking.sync.monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.sync.monitor.mark_processed"),
        patch("moonlighter.tracking.sync.monitor.get_or_create_label", return_value="Label_proc"),
    ):
        await sync_responses(SYNC_CONFIG, make_llm_caller(classify_result))

    notes = Application.get_by_id(application.id).notes
    assert existing_notes in notes
    assert "technical_interview" in notes or "interview" in notes


async def test_updated_at_refreshed_after_email_sync(temporary_database):
    init_db()
    job = make_job(temporary_database)
    old_time = datetime(2026, 1, 1)  # noqa: DTZ001 - the database stores naive local time
    application = make_application(job, status="submitted", email_ref="upd001", updated_at=old_time)

    classify_result = {
        "type": "rejection",
        "stage": None,
        "new_stage": None,
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "Rejeitado.",
    }
    message = {
        "to": "candidaturas+upd001@gmail.com",
        "from_": "hr@anthropic.com",
        "subject": "Update",
        "body": ".",
    }

    with (
        patch("moonlighter.tracking.sync.monitor.setup_gmail_service", return_value=MagicMock()),
        patch(
            "moonlighter.tracking.sync.monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.sync.monitor.parse_message", return_value=message),
        patch(
            "moonlighter.tracking.sync.monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.sync.monitor.mark_processed"),
        patch("moonlighter.tracking.sync.monitor.get_or_create_label", return_value="Label_proc"),
    ):
        await sync_responses(SYNC_CONFIG, make_llm_caller(classify_result))

    application_refreshed = Application.get_by_id(application.id)
    assert application_refreshed.updated_at > old_time
