"""The register_application tool: the service, worded for the conversation."""

from datetime import datetime

import pytest

from moonlighter.core.db import Application, Job, init_db
from moonlighter.mcp_tools.registration import register_application
from tests._context import make_test_context

NOVEMBER_10 = datetime(2026, 11, 10)  # noqa: DTZ001 - the database stores naive local time


def _context():
    return make_test_context(config={"email": {"address": "jane@example.com"}})


def _job(status="new"):
    init_db()
    return Job.create(
        source="manual", company="Acme", title="Eng", url="https://x/1", status=status
    )


async def test_registers_and_words_the_alias(temporary_database):
    job = _job(status="archived")
    text = await register_application(
        job.id, applied_at="2026-11-10", notes="applied on the site", context=_context()
    )
    application = Application.get(Application.job == job)
    assert text == (
        f"✓ Job #{job.id} (Acme/Eng): application registered, status → submitted\n"
        f"  Reply alias: jane+{application.email_ref}@example.com"
    )
    assert application.applied_at == NOVEMBER_10
    assert application.notes.endswith("] applied on the site")
    assert Job.get_by_id(job.id).status == "applied"


async def test_an_existing_row_is_reported_as_kept(temporary_database):
    job = _job()
    Application.create(job=job, status="rejected", email_ref="ab12cd34")
    text = await register_application(job.id, context=make_test_context(config={}))
    assert text == f"✓ Job #{job.id} (Acme/Eng): already registered, status stays rejected"


async def test_the_flag_reaches_the_row(temporary_database):
    job = _job()
    await register_application(job.id, reply_mailbox_unswept=True, context=_context())
    assert Application.get(Application.job == job).reply_mailbox_unswept is True


async def test_an_invalid_date_writes_nothing(temporary_database):
    job = _job()
    assert await register_application(job.id, applied_at="10/11/2026", context=_context()) == (
        "Invalid applied_at '10/11/2026': use YYYY-MM-DD."
    )
    assert Application.select().count() == 0


async def test_unknown_job_and_invalid_status_return_the_service_error(temporary_database):
    job = _job()
    assert await register_application(4242, context=_context()) == "Job 4242 not found."
    assert await register_application(job.id, status="hired", context=_context()) == (
        "Invalid status 'hired'. Accepted: submitted, screening, interviews, offer, rejected, "
        "no_response."
    )
    assert Application.select().count() == 0


@pytest.mark.parametrize("given", ["2026-11-10T15:30:00", "2026-11-10 15:30"])
async def test_a_date_with_a_time_is_refused_like_the_cli(temporary_database, given):
    job = _job()
    assert await register_application(job.id, applied_at=given, context=_context()) == (
        f"Invalid applied_at {given!r}: use YYYY-MM-DD."
    )
    assert Application.select().count() == 0


async def test_the_date_is_stored_at_midnight(temporary_database):
    job = _job()
    await register_application(job.id, applied_at="2026-11-10", context=_context())
    stored = Application.get(Application.job == job).applied_at
    assert stored == datetime(2026, 11, 10)  # noqa: DTZ001 - the database stores naive local time
