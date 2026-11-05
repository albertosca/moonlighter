"""A failed classification leaves the message for the next run; a spent quota stops the sync."""

from unittest.mock import MagicMock, patch

from moonlighter.core.db import Application, ProcessedEmail, init_db
from moonlighter.tracking.email_monitor import sync_responses

from tests.tracking.llm_callers import make_llm_caller
from tests.tracking.pipeline_rows import make_application, make_job
from tests.tracking.sync_setup import SYNC_CONFIG

# ── failure signalling end-to-end (whole-branch Finding 1) ─────────────


async def test_llm_failure_does_not_burn_the_message_and_retries_on_next_sync(temporary_database):
    """Proves Finding 1 end-to-end, through the real classify_response (not
    mocked): an LLM failure during classification must not mark the message
    processed. It has to survive to be retried by a later sync with a
    healthy LLM. Revert the classification.py/email_monitor.py fix (make
    classify_response fall back to _classification_from({}) on any
    exception, and drop the try/except around it in _classify) and
    this test fails — the first sync marks msg0 processed via the
    'unrelated' fallback, so the second sync's healthy caller never even
    gets invoked for it."""
    init_db()
    job = make_job(temporary_database)
    application = make_application(job, status="submitted", email_ref="fail001")

    message = {
        "to": "candidaturas+fail001@gmail.com",
        "from_": "hr@anthropic.com",
        "subject": "Technical interview",
        "body": "We would like to schedule an interview.",
    }

    async def raising_caller(prompt, model, cache_prefix=None):
        raise RuntimeError("transient LLM error")

    with (
        patch("moonlighter.tracking.email_monitor.setup_gmail_service", return_value=MagicMock()),
        patch(
            "moonlighter.tracking.email_monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.email_monitor.parse_message", return_value=message),
        patch("moonlighter.tracking.email_monitor.mark_processed"),
        patch("moonlighter.tracking.email_monitor.get_or_create_label", return_value="Label_proc"),
    ):
        first_updates = await sync_responses(SYNC_CONFIG, raising_caller)

    assert first_updates == []
    assert not ProcessedEmail.select().where(ProcessedEmail.message_id == "msg0").exists()
    assert Application.get_by_id(application.id).status == "submitted"  # untouched

    healthy_result = {
        "type": "interview",
        "stage": "technical_interview",
        "new_stage": None,
        "company": "Anthropic",
        "job_title": "Senior Engineer",
        "summary": "Technical interview scheduled.",
    }

    with (
        patch("moonlighter.tracking.email_monitor.setup_gmail_service", return_value=MagicMock()),
        patch(
            "moonlighter.tracking.email_monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.email_monitor.parse_message", return_value=message),
        patch("moonlighter.tracking.email_monitor.mark_processed"),
        patch("moonlighter.tracking.email_monitor.get_or_create_label", return_value="Label_proc"),
    ):
        second_updates = await sync_responses(SYNC_CONFIG, make_llm_caller(healthy_result))

    assert len(second_updates) == 1
    assert ProcessedEmail.select().where(ProcessedEmail.message_id == "msg0").exists()
    assert Application.get_by_id(application.id).status == "interviews"


async def test_spend_limit_stops_the_loop_instead_of_burning_remaining_messages(temporary_database):
    """A spend-limit failure must stop the sync loop outright, not just skip
    the failing message: retrying every remaining message against a dead
    quota wastes the whole batch. Proven by call count — parse_message must
    only be invoked once, for the message that hit the limit; the second
    message is never even looked at."""
    init_db()
    job1 = make_job(temporary_database)
    application1 = make_application(job1, status="submitted", email_ref="sl001")
    job2 = make_job(temporary_database, url="https://boards.greenhouse.io/anthropic/jobs/2")
    application2 = make_application(job2, status="submitted", email_ref="sl002")

    messages = {
        "msg0": {
            "to": "candidaturas+sl001@gmail.com",
            "from_": "hr@a.com",
            "subject": "x",
            "body": "y",
        },
        "msg1": {
            "to": "candidaturas+sl002@gmail.com",
            "from_": "hr@a.com",
            "subject": "x",
            "body": "y",
        },
    }

    async def spend_limit_caller(prompt, model, cache_prefix=None):
        raise RuntimeError("rate limit exceeded, please retry later")

    parse_mock = MagicMock(side_effect=lambda service, mid: messages[mid])

    with (
        patch("moonlighter.tracking.email_monitor.setup_gmail_service", return_value=MagicMock()),
        patch(
            "moonlighter.tracking.email_monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}, {"id": "msg1", "threadId": "t1"}],
        ),
        patch("moonlighter.tracking.email_monitor.parse_message", parse_mock),
        patch("moonlighter.tracking.email_monitor.mark_processed"),
        patch("moonlighter.tracking.email_monitor.get_or_create_label", return_value="Label_proc"),
    ):
        updates = await sync_responses(SYNC_CONFIG, spend_limit_caller)

    assert updates == []
    assert parse_mock.call_count == 1  # the loop stopped after the first spend-limit hit
    assert ProcessedEmail.select().count() == 0  # neither message was burned
    assert Application.get_by_id(application1.id).status == "submitted"
    assert Application.get_by_id(application2.id).status == "submitted"
