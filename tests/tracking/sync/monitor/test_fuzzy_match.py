"""A reply without a reference is only ever a suggestion, never a pipeline change."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Application, init_db
from moonlighter.tracking.sync.monitor import sync_responses

from tests.tracking.llm_callers import make_llm_caller
from tests.tracking.pipeline_rows import make_application, make_job
from tests.tracking.sync_setup import SYNC_CONFIG
from tests.tracking.tracking_settings import BASE_EMAIL


async def test_email_without_ref_fuzzy_match_is_suggestion_only(temporary_database):
    """S-06: fuzzy match (no +ref) never mutates the pipeline — it's a
    suggestion the human must confirm via update_status. Anyone who knows a
    real company name can otherwise forge a rejection/interview email that
    silently mutates a real application.
    """
    init_db()
    job = make_job(temporary_database, company="Stripe", title="Backend Engineer")
    application = make_application(job, status="submitted", email_ref=None)

    message = {
        "to": BASE_EMAIL,
        "from_": "talent@stripe.com",
        "subject": "Next steps",
        "body": "Hi, moving forward with your application for Backend Engineer.",
    }
    classify_result = {
        "type": "interview",
        "stage": "technical_interview",
        "new_stage": None,
        "company": "Stripe",
        "job_title": "Backend Engineer",
        "summary": "Technical interview.",
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
        updates = await sync_responses(SYNC_CONFIG, make_llm_caller(classify_result))

    application_refreshed = Application.get_by_id(application.id)
    assert application_refreshed.status == "submitted"  # NOT mutated
    assert len(updates) == 1
    assert updates[0]["match_type"] == "fuzzy"
    assert updates[0]["needs_confirmation"] is True
    assert updates[0]["suggested_job_id"] == job.id


async def test_fuzzy_rejection_never_auto_rejects(temporary_database):
    """The exact S-06 attack: a forged rejection naming a real company,
    without the +ref alias, must never flip a real application to the
    terminal 'rejected' status.
    """
    init_db()
    job = make_job(temporary_database, company="Anthropic", title="Senior Engineer")
    application = make_application(job, status="submitted", email_ref=None)

    message = {
        "to": BASE_EMAIL,
        "from_": "someone@example.com",
        "subject": "Your application",
        "body": "Unfortunately we won't be moving forward with your Senior Engineer application.",
    }
    classify_result = {
        "type": "rejection",
        "stage": None,
        "new_stage": None,
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "Forged rejection, no ref.",
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
        updates = await sync_responses(SYNC_CONFIG, make_llm_caller(classify_result))

    assert (
        Application.get_by_id(application.id).status == "submitted"
    )  # NEVER turns rejected without ref
    assert updates[0]["needs_confirmation"] is True


async def test_ambiguous_match_marks_uncertain_in_notes(temporary_database):
    init_db()
    job1 = make_job(temporary_database, company="Stripe", title="Engineer", url="https://x.com/1")
    job2 = make_job(temporary_database, company="Stripe", title="Engineer", url="https://x.com/2")
    make_application(job1, status="submitted", email_ref=None)
    make_application(job2, status="submitted", email_ref=None)

    message = {
        "to": BASE_EMAIL,
        "from_": "hr@stripe.com",
        "subject": "Update",
        "body": "Seguindo com sua candidatura para Engineer.",
    }
    classify_result = {
        "type": "interview",
        "stage": "phone_screening",
        "new_stage": None,
        "company": "Stripe",
        "job_title": "Engineer",
        "summary": "Initial call.",
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
        updates = await sync_responses(SYNC_CONFIG, make_llm_caller(classify_result))

    # No application can have been updated for certain — uncertain
    assert any("uncertain" in (update.get("match_type", "")) for update in updates)
