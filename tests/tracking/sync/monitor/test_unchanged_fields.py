"""Replies that must leave the status and stage as they are."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Application, init_db
from moonlighter.tracking.sync.monitor import sync_responses

from tests.tracking.llm_callers import make_llm_caller
from tests.tracking.pipeline_rows import make_application, make_job
from tests.tracking.sync_setup import SYNC_CONFIG
from tests.tracking.tracking_settings import BASE_STAGES


async def test_info_request_keeps_current_status(temporary_database):
    init_db()
    job = make_job(temporary_database)
    application = make_application(job, status="screening", email_ref="inf001")

    classify_result = {
        "type": "info_request",
        "stage": None,
        "new_stage": None,
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "We need more information.",
    }
    message = {
        "to": "candidaturas+inf001@gmail.com",
        "from_": "hr@anthropic.com",
        "subject": "Information",
        "body": "Can you send us your portfolio?",
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

    assert Application.get_by_id(application.id).status == "screening"


async def test_hallucinated_stage_not_in_known_list_is_ignored(temporary_database):
    """S-05: a 'stage' outside the known list (and that isn't a declared
    new_stage) is never written to current_stage — mitigates hallucination
    via prompt injection (S-04) even if it escapes the delimiter.
    """
    init_db()
    job = make_job(temporary_database)
    application = make_application(job, status="submitted", email_ref="hal001", current_stage=None)

    classify_result = {
        "type": "interview",
        "stage": "made_up_stage_not_registered",
        "new_stage": None,
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "Attempted fabricated internship.",
    }
    message = {
        "to": "candidaturas+hal001@gmail.com",
        "from_": "hr@anthropic.com",
        "subject": "Update",
        "body": "x",
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
    assert (
        application_refreshed.status == "interviews"
    )  # the type still advances (it's trustworthy)
    assert application_refreshed.current_stage is None  # the made-up stage is discarded


# ── acknowledgement end-to-end (whole-branch Finding 4) ─────────────────


async def test_acknowledgement_end_to_end_leaves_status_and_stage_untouched(temporary_database):
    """End-to-end proof (through the real classify_response, not mocked)
    that an acknowledgement email never advances status or writes a stage —
    even when the LLM volunteers a stage/new_stage alongside
    'acknowledgement', which real ATS receipts sometimes do. This holds
    only because classify_response's _classification_from strips
    stage/new_stage for acknowledgement BEFORE register_new_stage and
    advance_application run in _apply_reply; if that stripping ever
    regressed, register_new_stage would register the volunteered stage as
    legitimately new, and advance_application would then find it 'known'
    and write it to current_stage. That coupling was previously untested —
    this is the test that would catch a regression in it.
    """
    init_db()
    job = make_job(temporary_database)
    application = make_application(job, status="submitted", email_ref="ack001", current_stage=None)

    message = {
        "to": "candidaturas+ack001@gmail.com",
        "from_": "noreply@anthropic.com",
        "subject": "Application received",
        "body": "Thank you for applying! We have received your application.",
    }
    llm_reply = {
        "type": "acknowledgement",
        "stage": "onboarding_call",
        "new_stage": "onboarding_call",  # not in BASE_STAGES — would register if not stripped
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "Application received.",
    }
    config = {
        **SYNC_CONFIG,
        "email": {**SYNC_CONFIG["email"], "interview_stages": list(BASE_STAGES)},
    }

    with (
        patch("moonlighter.tracking.sync.monitor.setup_gmail_service", return_value=MagicMock()),
        patch(
            "moonlighter.tracking.sync.monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.sync.monitor.parse_message", return_value=message),
        patch("moonlighter.tracking.sync.monitor.mark_processed"),
        patch("moonlighter.tracking.sync.monitor.get_or_create_label", return_value="Label_proc"),
    ):
        updates = await sync_responses(config, make_llm_caller(llm_reply))

    application_refreshed = Application.get_by_id(application.id)
    assert application_refreshed.status == "submitted"  # unchanged
    assert application_refreshed.current_stage is None  # unchanged
    assert "acknowledgement" in application_refreshed.notes
    assert "onboarding_call" not in config["email"]["interview_stages"]  # not registered
    assert len(updates) == 1
