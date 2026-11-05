"""Registering a new interview stage from a reply, only on a reference match."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Application, init_db
from moonlighter.tracking.sync.monitor import sync_responses

from tests.tracking.llm_callers import make_llm_caller
from tests.tracking.pipeline_rows import make_application, make_job
from tests.tracking.sync_setup import SYNC_CONFIG
from tests.tracking.tracking_settings import BASE_EMAIL, BASE_STAGES


async def test_new_stage_added_to_config(temporary_database):
    init_db()
    job = make_job(temporary_database)
    make_application(job, status="submitted", email_ref="new001")

    classify_result = {
        "type": "interview",
        "stage": "pair_programming",
        "new_stage": "pair_programming",
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "Pair programming session.",
    }
    message = {
        "to": "candidaturas+new001@gmail.com",
        "from_": "hr@anthropic.com",
        "subject": "Pair session",
        "body": "Vamos fazer pair programming.",
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
        patch(
            "moonlighter.tracking.sync.monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.sync.monitor.mark_processed"),
        patch("moonlighter.tracking.sync.monitor.get_or_create_label", return_value="Label_proc"),
    ):
        await sync_responses(config, make_llm_caller(classify_result))

    assert "pair_programming" in config["email"]["interview_stages"]


async def test_fuzzy_match_never_registers_a_new_stage(temporary_database):
    """S-06 hardening: a spoofed email (no ref) that proposes a new_stage
    must not get it registered into the shared interview_stages config —
    only a ref-confirmed match may influence anything, including stage
    registration.
    """
    init_db()
    job = make_job(temporary_database, company="Stripe", title="Backend Engineer")
    make_application(job, status="submitted", email_ref=None)

    message = {
        "to": BASE_EMAIL,
        "from_": "someone@example.com",
        "subject": "Update",
        "body": "Moving forward with a custom_spoofed_stage for Backend Engineer.",
    }
    classify_result = {
        "type": "interview",
        "stage": "custom_spoofed_stage",
        "new_stage": "custom_spoofed_stage",
        "company": "Stripe",
        "job_title": "Backend Engineer",
        "summary": "Spoofed stage proposal.",
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
        patch(
            "moonlighter.tracking.sync.monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.sync.monitor.mark_processed"),
        patch("moonlighter.tracking.sync.monitor.get_or_create_label", return_value="Label_proc"),
    ):
        await sync_responses(config, make_llm_caller(classify_result))

    assert "custom_spoofed_stage" not in config["email"]["interview_stages"]


async def test_legitimately_registered_new_stage_is_accepted(temporary_database):
    """A declared new_stage (registered via register_new_stage BEFORE
    advance_application runs) must be accepted — it's not hallucination,
    it's a deliberate feature.
    """
    init_db()
    job = make_job(temporary_database)
    application = make_application(job, status="submitted", email_ref="ns001", current_stage=None)

    classify_result = {
        "type": "interview",
        "stage": "pair_programming",
        "new_stage": "pair_programming",
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "Pair programming session.",
    }
    message = {
        "to": "candidaturas+ns001@gmail.com",
        "from_": "hr@anthropic.com",
        "subject": "Pair session",
        "body": "x",
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
        patch(
            "moonlighter.tracking.sync.monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.sync.monitor.mark_processed"),
        patch("moonlighter.tracking.sync.monitor.get_or_create_label", return_value="Label_proc"),
    ):
        await sync_responses(config, make_llm_caller(classify_result))

    assert Application.get_by_id(application.id).current_stage == "pair_programming"
