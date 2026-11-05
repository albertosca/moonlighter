"""update_status accepts the documented statuses, keeps the job in step and refuses the rest."""

import re

import pytest
from moonlighter.core.db import Application, Job, init_db
from moonlighter.mcp_tools.applications import update_status

from tests.mcp_tools._records import create_application, create_job


async def test_update_status_success(temporary_database):
    init_db()
    job = create_job(temporary_database, url="https://x.com/us1")
    create_application(job)

    result = await update_status(job_id=job.id, status="screening")
    app = Application.get(Application.job == job)
    assert app.status == "screening"
    assert "screening" in result


async def test_update_status_documents_exactly_the_accepted_statuses(temporary_database):
    # The MCP client is an LLM that follows the docstring: a documented
    # 'interview' against an accepted 'interviews' made correct-looking calls fail.

    init_db()
    job = create_job(temporary_database, url="https://x.com/us-doc")
    create_application(job)

    docstring_line = next(
        line for line in (update_status.__doc__ or "").splitlines() if "status:" in line
    )
    documented = set(re.findall(r"'([a-z_]+)'", docstring_line))
    rejection = await update_status(job_id=job.id, status="?")
    accepted = set(rejection.split("Accepted values: ")[1].split(", "))
    assert documented == accepted


async def test_update_status_syncs_job_status(temporary_database):
    # 2026-08-21: 5 jobs sat 'new' with a real submitted Application — the
    # queue nearly offered a duplicate application twice in one session.
    init_db()
    job = create_job(temporary_database, url="https://x.com/us-sync")
    create_application(job)

    await update_status(job_id=job.id, status="submitted")
    assert Job.get_by_id(job.id).status == "applied"

    await update_status(job_id=job.id, status="rejected")
    assert Job.get_by_id(job.id).status == "rejected"


async def test_update_status_invalid(temporary_database):
    init_db()

    result = await update_status(job_id=1, status="banana")
    assert "Invalid" in result or "Status" in result


async def test_update_status_job_not_found(temporary_database):
    init_db()

    result = await update_status(job_id=77777, status="screening")
    assert "not found" in result


async def test_update_status_no_application(temporary_database):
    init_db()
    job = create_job(temporary_database, url="https://x.com/us5")
    # No application

    result = await update_status(job_id=job.id, status="screening")
    assert "application" in result or "not found" in result


async def test_update_status_invalid_leaves_db_untouched(temporary_database):
    """An invalid status must be rejected before any DB write — no partial mutation."""
    init_db()
    job = create_job(temporary_database, url="https://x.com/us6")
    create_application(job, status="draft", notes="original notes")

    result = await update_status(job_id=job.id, status="banana", notes="should not stick")
    app = Application.get(Application.job == job)
    assert app.status == "draft"
    assert app.notes == "original notes"
    assert "Invalid" in result


@pytest.mark.parametrize(
    "status",
    ["screening", "interviews", "offer", "rejected", "submitted", "draft"],
)
async def test_update_status_accepts_every_valid_status(temporary_database, status):
    """Every documented status value in the `valid` set is actually accepted."""
    init_db()
    job = create_job(temporary_database, url=f"https://x.com/us-valid-{status}")
    create_application(job)

    result = await update_status(job_id=job.id, status=status)
    app = Application.get(Application.job == job)
    assert app.status == status
    assert status in result


async def test_update_status_invalid_lists_accepted_values_sorted(temporary_database):
    """Error message enumerates the accepted statuses, alphabetically sorted."""
    init_db()

    result = await update_status(job_id=1, status="not-a-real-status")
    expected_order = ", ".join(
        sorted({"screening", "interviews", "offer", "rejected", "submitted", "draft"})
    )
    assert expected_order in result


async def test_update_status_job_not_found_does_not_leak_other_jobs(temporary_database):
    """A missing job_id returns the not-found message without touching unrelated rows."""
    init_db()
    job = create_job(temporary_database, url="https://x.com/us10")
    create_application(job, status="draft")

    result = await update_status(job_id=999999, status="offer")
    assert "not found" in result
    app = Application.get(Application.job == job)
    assert app.status == "draft"  # untouched
