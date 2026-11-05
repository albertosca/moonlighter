"""reopen_job brings back only an archived job."""

from datetime import datetime

from moonlighter.core.db import Job, init_db
from moonlighter.mcp_tools.jobs import reopen_job

from tests.mcp_tools._records import create_job


async def test_reopen_job_brings_an_archived_job_back_to_reviewed(temporary_database):
    """Before this tool the only way to try an archived job anyway was editing the
    DB by hand (Encora #8314/#8315, 2026-09-24)."""

    init_db()
    job = create_job(
        temporary_database,
        url="https://x.com/reopen1",
        status="archived",
        closed_at=datetime(2026, 9, 1),  # noqa: DTZ001 - the models store naive local timestamps, so the test builds one the same way
    )

    result = await reopen_job(job_id=job.id)
    reopened = Job.get_by_id(job.id)
    assert reopened.status == "reviewed"
    assert reopened.closed_at is None
    assert f"#{job.id}" in result
    assert "reviewed" in result


async def test_reopen_job_refuses_a_job_that_is_not_archived(temporary_database):
    init_db()
    job = create_job(temporary_database, url="https://x.com/reopen2", status="applied")

    result = await reopen_job(job_id=job.id)
    assert Job.get_by_id(job.id).status == "applied"
    assert "not archived" in result
    assert "applied" in result


async def test_reopen_job_reports_an_unknown_id(temporary_database):
    init_db()

    result = await reopen_job(job_id=999)
    assert "not found" in result
