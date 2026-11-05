"""An email that advances an application feeds the answer bank, and one that does not leaves it alone."""

from unittest.mock import AsyncMock, patch

from moonlighter.core.db import AnswerBankEntry, init_db
from moonlighter.mcp_tools.email_tracking import sync_email_responses
from tests._context import make_test_context
from tests.mcp_tools._records import create_application, create_job


async def test_sync_email_responses_promotes_the_answers_of_an_application_an_email_advanced(
    temporary_database,
):
    """The bank's only promotion trigger used to be update_status(..., 'submitted').
    An application whose status only ever advances because a reply arrived by
    email never passed through it, so its answers were never promoted — the
    shared bank filled far more slowly than the design assumed.
    """
    init_db()

    job = create_job(temporary_database, url="https://boards.greenhouse.io/acme/jobs/931")
    create_application(
        job,
        status="submitted",
        form_data='{"Are you authorized to work in Brazil?": {"answer": "Yes", "kind": "boolean"}}',
    )

    fake_updates = [
        {
            "company": "Acme",
            "title": "Staff Engineer",
            "type": "interview",
            "stage": None,
            "match_type": "ref",
            "job_id": job.id,
            "status_advanced": True,
        }
    ]

    with patch(
        "moonlighter.mcp_tools.email_tracking.sync_responses",
        new=AsyncMock(return_value=fake_updates),
    ):
        await sync_email_responses(context=make_test_context(config={"email": {}}))

    row = AnswerBankEntry.get(
        AnswerBankEntry.normalized_question == "are you authorized to work in brazil"
    )
    assert row.answer == "Yes"
    assert row.source_job_id == job.id


async def test_sync_email_responses_does_not_promote_when_the_status_did_not_advance(
    temporary_database,
):
    """An acknowledgement matches a real ref but moves nothing. A fuzzy match
    (S-06) never mutates the application at all. Neither is evidence to promote
    on — promotion follows the advance, not the arrival of an email.
    """
    init_db()

    job = create_job(temporary_database, url="https://boards.greenhouse.io/acme/jobs/932")
    create_application(
        job,
        status="submitted",
        form_data='{"Notice period": {"answer": "30 days", "kind": "text"}}',
    )

    fake_updates = [
        {
            "company": "Acme",
            "title": "Staff Engineer",
            "type": "acknowledgement",
            "stage": None,
            "match_type": "ref",
            "job_id": job.id,
            "status_advanced": False,
        },
        {
            "company": "Acme",
            "title": "Staff Engineer",
            "type": "rejection",
            "stage": None,
            "match_type": "fuzzy",
            "job_id": None,
            "status_advanced": False,
            "suggested_job_id": job.id,
            "needs_confirmation": True,
        },
    ]

    with patch(
        "moonlighter.mcp_tools.email_tracking.sync_responses",
        new=AsyncMock(return_value=fake_updates),
    ):
        await sync_email_responses(context=make_test_context(config={"email": {}}))

    assert AnswerBankEntry.select().count() == 0
