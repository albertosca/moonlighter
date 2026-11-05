"""Which messages a sync records as processed, and what it writes to Gmail."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Application, ProcessedEmail, init_db
from moonlighter.tracking.email_monitor import sync_responses

from tests.tracking.llm_callers import make_llm_caller
from tests.tracking.pipeline_rows import make_application, make_job
from tests.tracking.sync_setup import SYNC_CONFIG
from tests.tracking.tracking_settings import BASE_EMAIL


async def test_unrelated_email_skipped_and_marked_processed(temporary_database):
    init_db()
    job = make_job(temporary_database)
    application = make_application(job, status="submitted", email_ref="unr001")

    classify_result = {
        "type": "unrelated",
        "stage": None,
        "new_stage": None,
        "company": None,
        "job_title": None,
        "summary": "Newsletter de marketing.",
    }
    message = {
        "to": "candidaturas+unr001@gmail.com",
        "from_": "news@company.com",
        "subject": "Promotion!",
        "body": "Confira nossas ofertas.",
    }

    with (
        patch("moonlighter.tracking.email_monitor.setup_gmail_service", return_value=MagicMock()),
        patch(
            "moonlighter.tracking.email_monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.email_monitor.parse_message", return_value=message),
        patch(
            "moonlighter.tracking.email_monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.email_monitor.mark_processed") as mock_mark,
        patch("moonlighter.tracking.email_monitor.get_or_create_label", return_value="Label_proc"),
    ):
        updates = await sync_responses(SYNC_CONFIG, make_llm_caller(classify_result))

    # Application was not touched
    assert Application.get_by_id(application.id).status == "submitted"
    # Read-only by default: Gmail not touched, but the email is recorded locally.
    mock_mark.assert_not_called()
    assert ProcessedEmail.select().where(ProcessedEmail.message_id == "msg0").exists()
    # Does not return an update for unrelated
    assert len(updates) == 0


async def test_every_email_recorded_locally_without_gmail_writes(temporary_database):
    """Read-only by default: no email is touched on Gmail; each one is recorded
    locally in ProcessedEmail.
    """
    init_db()
    classify_result = {
        "type": "unrelated",
        "stage": None,
        "new_stage": None,
        "company": None,
        "job_title": None,
        "summary": "Spam.",
    }
    messages = [
        {"to": BASE_EMAIL, "from_": "a@a.com", "subject": "A", "body": "a"},
        {"to": BASE_EMAIL, "from_": "b@b.com", "subject": "B", "body": "b"},
        {"to": BASE_EMAIL, "from_": "c@c.com", "subject": "C", "body": "c"},
    ]
    raw_ids = [{"id": f"msg{index}", "threadId": f"t{index}"} for index in range(3)]

    with (
        patch("moonlighter.tracking.email_monitor.setup_gmail_service", return_value=MagicMock()),
        patch("moonlighter.tracking.email_monitor.fetch_recent_messages", return_value=raw_ids),
        patch("moonlighter.tracking.email_monitor.parse_message", side_effect=messages),
        patch(
            "moonlighter.tracking.email_monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.email_monitor.mark_processed") as mock_mark,
        patch("moonlighter.tracking.email_monitor.get_or_create_label") as mock_label,
    ):
        await sync_responses(SYNC_CONFIG, make_llm_caller(classify_result))

    mock_mark.assert_not_called()  # nothing written to Gmail
    mock_label.assert_not_called()  # not even the label is created
    assert ProcessedEmail.select().count() == 3


async def test_mark_processed_only_when_opted_in(temporary_database):
    """With email.mark_processed=True, Gmail is mutated (marks read + label)."""
    init_db()
    classify_result = {
        "type": "unrelated",
        "stage": None,
        "new_stage": None,
        "company": None,
        "job_title": None,
        "summary": "Spam.",
    }
    messages = [{"to": BASE_EMAIL, "from_": "a@a.com", "subject": "A", "body": "a"}]
    raw_ids = [{"id": "msg0", "threadId": "t0"}]
    config = {**SYNC_CONFIG, "email": {**SYNC_CONFIG["email"], "mark_processed": True}}

    with (
        patch("moonlighter.tracking.email_monitor.setup_gmail_service", return_value=MagicMock()),
        patch("moonlighter.tracking.email_monitor.fetch_recent_messages", return_value=raw_ids),
        patch("moonlighter.tracking.email_monitor.parse_message", side_effect=messages),
        patch(
            "moonlighter.tracking.email_monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.email_monitor.mark_processed") as mock_mark,
        patch("moonlighter.tracking.email_monitor.get_or_create_label", return_value="Label_proc"),
    ):
        await sync_responses(config, make_llm_caller(classify_result))

    mock_mark.assert_called_once()


async def test_already_processed_email_is_skipped(temporary_database):
    """An email already recorded in ProcessedEmail is not reprocessed (no re-calling the LLM)."""
    init_db()
    ProcessedEmail.create(message_id="msg0")
    classify_mock = AsyncMock(
        return_value={
            "type": "unrelated",
            "stage": None,
            "new_stage": None,
            "company": None,
            "job_title": None,
            "summary": "",
        }
    )

    with (
        patch("moonlighter.tracking.email_monitor.setup_gmail_service", return_value=MagicMock()),
        patch(
            "moonlighter.tracking.email_monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.email_monitor.parse_message") as mock_parse,
        patch("moonlighter.tracking.email_monitor.classify_response", new=classify_mock),
    ):
        updates = await sync_responses(SYNC_CONFIG, make_llm_caller({}))

    mock_parse.assert_not_called()  # not even parsed
    classify_mock.assert_not_called()  # not even classified
    assert updates == []


async def test_returns_empty_list_when_no_emails(temporary_database):
    init_db()
    with (
        patch("moonlighter.tracking.email_monitor.setup_gmail_service", return_value=MagicMock()),
        patch("moonlighter.tracking.email_monitor.fetch_recent_messages", return_value=[]),
        patch("moonlighter.tracking.email_monitor.get_or_create_label", return_value="Label_proc"),
    ):
        updates = await sync_responses(SYNC_CONFIG, make_llm_caller({}))

    assert updates == []
