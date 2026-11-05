"""A reply carrying its reference updates the application, never backwards."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Application, ProcessedEmail, init_db
from moonlighter.tracking.sync.monitor import sync_responses

from tests.tracking.llm_callers import make_llm_caller
from tests.tracking.pipeline_rows import make_application, make_job
from tests.tracking.sync_setup import SYNC_CONFIG, mock_service


async def test_email_with_ref_updates_application_status(temporary_database):
    init_db()
    job = make_job(temporary_database)
    application = make_application(job, status="submitted", email_ref="x7k2mp")

    messages = [
        {
            "to": "candidaturas+x7k2mp@gmail.com",
            "from_": "hr@anthropic.com",
            "subject": "Technical interview",
            "body": "Hello, we would like to schedule an interview.",
        }
    ]
    classify_result = {
        "type": "interview",
        "stage": "technical_interview",
        "new_stage": None,
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "Technical interview scheduled.",
    }

    service = mock_service(messages)

    with (
        patch("moonlighter.tracking.sync.monitor.setup_gmail_service", return_value=service),
        patch(
            "moonlighter.tracking.sync.monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.sync.monitor.parse_message", return_value=messages[0]),
        patch(
            "moonlighter.tracking.sync.monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.sync.monitor.mark_processed") as mock_mark,
        patch("moonlighter.tracking.sync.monitor.get_or_create_label", return_value="Label_proc"),
    ):
        updates = await sync_responses(SYNC_CONFIG, make_llm_caller(classify_result))

    application_refreshed = Application.get_by_id(application.id)
    assert application_refreshed.status == "interviews"
    assert application_refreshed.current_stage == "technical_interview"
    assert "[" in application_refreshed.notes  # has a date
    assert "match: ref" in application_refreshed.notes
    # Read-only by default: Gmail is not touched; dedup is local (ProcessedEmail).
    mock_mark.assert_not_called()
    assert ProcessedEmail.select().where(ProcessedEmail.message_id == "msg0").exists()
    assert len(updates) == 1


async def test_rejection_sets_status_rejected(temporary_database):
    init_db()
    job = make_job(temporary_database)
    application = make_application(job, status="submitted", email_ref="rej001")

    classify_result = {
        "type": "rejection",
        "stage": None,
        "new_stage": None,
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "We won't be moving forward with your application.",
    }
    message = {
        "to": "candidaturas+rej001@gmail.com",
        "from_": "noreply@anthropic.com",
        "subject": "Sua candidatura",
        "body": "Obrigado pelo interesse.",
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

    assert Application.get_by_id(application.id).status == "rejected"


async def test_status_never_regresses(temporary_database):
    """A screening email must not regress an application already in 'interviews'."""
    init_db()
    job = make_job(temporary_database)
    application = make_application(
        job, status="interviews", email_ref="nrg001", current_stage="technical_interview"
    )

    classify_result = {
        "type": "screening",
        "stage": "phone_screening",
        "new_stage": None,
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "We've scheduled an initial call.",
    }
    message = {
        "to": "candidaturas+nrg001@gmail.com",
        "from_": "hr@anthropic.com",
        "subject": "Call",
        "body": "Let's schedule a call.",
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
    assert application_refreshed.status == "interviews"  # did not regress
