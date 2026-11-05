"""The report entries a sync returns, through sync_responses: the job and whether the status advanced."""

from unittest.mock import AsyncMock, patch

from moonlighter.core.db import init_db
from moonlighter.tracking.email_monitor import sync_responses

from tests.tracking.llm_callers import make_llm_caller
from tests.tracking.pipeline_rows import make_application, make_job
from tests.tracking.sync_setup import SYNC_CONFIG, mock_service


async def test_ref_match_reports_the_db_job_not_the_email_guess(temporary_database):
    # The classifier reads company/title off the EMAIL and often can't
    # (rejections rarely repeat the title) — but a ref match already knows
    # the exact Job. The update must carry the DB truth, not "?" material.
    init_db()
    job = make_job(temporary_database, company="Acme Robotics", title="Staff Engineer")
    make_application(job, status="submitted", email_ref="q9ref1")

    messages = [
        {
            "to": "candidaturas+q9ref1@gmail.com",
            "from_": "no-reply@acme.com",
            "subject": "Your application",
            "body": "Thank you for applying. We will not move forward.",
        }
    ]
    classify_result = {
        "type": "rejection",
        "stage": None,
        "new_stage": None,
        "company": None,
        "job_title": None,
        "summary": "Rejection.",
    }
    service = mock_service(messages)

    with (
        patch("moonlighter.tracking.email_monitor.setup_gmail_service", return_value=service),
        patch(
            "moonlighter.tracking.email_monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.email_monitor.parse_message", return_value=messages[0]),
        patch(
            "moonlighter.tracking.email_monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.email_monitor.get_or_create_label", return_value="Label_proc"),
    ):
        updates = await sync_responses(SYNC_CONFIG, make_llm_caller(classify_result))

    assert len(updates) == 1
    assert updates[0]["company"] == "Acme Robotics"
    assert updates[0]["title"] == "Staff Engineer"


async def test_a_ref_match_that_advances_the_status_reports_the_job_id_and_the_advance(
    temporary_database,
):
    # The answer bank is promoted at the composition root (server.py), which
    # only sees this list of updates — so an update has to carry enough to
    # tell "this application really moved forward" from "nothing changed".
    # Without job_id the promoter cannot find the Application at all.
    init_db()
    job = make_job(temporary_database)
    make_application(job, status="submitted", email_ref="adv1ref")

    messages = [
        {
            "to": "candidaturas+adv1ref@gmail.com",
            "from_": "hr@anthropic.com",
            "subject": "Interview",
            "body": "We would like to schedule an interview.",
        }
    ]
    classify_result = {
        "type": "interview",
        "stage": None,
        "new_stage": None,
        "company": None,
        "job_title": None,
        "summary": "Interview scheduled.",
    }

    with (
        patch(
            "moonlighter.tracking.email_monitor.setup_gmail_service",
            return_value=mock_service(messages),
        ),
        patch(
            "moonlighter.tracking.email_monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.email_monitor.parse_message", return_value=messages[0]),
        patch(
            "moonlighter.tracking.email_monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.email_monitor.get_or_create_label", return_value="Label_proc"),
    ):
        updates = await sync_responses(SYNC_CONFIG, make_llm_caller(classify_result))

    assert updates[0]["job_id"] == job.id
    assert updates[0]["status_advanced"] is True


async def test_a_ref_match_that_moves_nothing_reports_no_advance(temporary_database):
    # An acknowledgement ("we received your application") is a real reply on
    # a real ref, but _TYPE_TO_STATUS maps it to nothing — the status does
    # not move, so this must not read as an advance.
    init_db()
    job = make_job(temporary_database)
    make_application(job, status="submitted", email_ref="noadvref")

    messages = [
        {
            "to": "candidaturas+noadvref@gmail.com",
            "from_": "no-reply@anthropic.com",
            "subject": "Received",
            "body": "We have received your application.",
        }
    ]
    classify_result = {
        "type": "acknowledgement",
        "stage": None,
        "new_stage": None,
        "company": None,
        "job_title": None,
        "summary": "Received.",
    }

    with (
        patch(
            "moonlighter.tracking.email_monitor.setup_gmail_service",
            return_value=mock_service(messages),
        ),
        patch(
            "moonlighter.tracking.email_monitor.fetch_recent_messages",
            return_value=[{"id": "msg0", "threadId": "t0"}],
        ),
        patch("moonlighter.tracking.email_monitor.parse_message", return_value=messages[0]),
        patch(
            "moonlighter.tracking.email_monitor.classify_response",
            new=AsyncMock(return_value=classify_result),
        ),
        patch("moonlighter.tracking.email_monitor.get_or_create_label", return_value="Label_proc"),
    ):
        updates = await sync_responses(SYNC_CONFIG, make_llm_caller(classify_result))

    assert updates[0]["job_id"] == job.id
    assert updates[0]["status_advanced"] is False
