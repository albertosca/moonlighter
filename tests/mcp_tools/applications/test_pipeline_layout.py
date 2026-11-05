"""How get_pipeline groups, orders and counts the applications."""

from datetime import timedelta

from moonlighter.core.db import Application, init_db
from moonlighter.mcp_tools.applications import get_pipeline

from tests._context import make_test_context
from tests.mcp_tools._records import create_application, create_job


async def test_get_pipeline_empty(temporary_database):
    init_db()

    result = await get_pipeline(context=make_test_context())
    assert "0" in result or "Total" in result


async def test_get_pipeline_groups_by_status(temporary_database):
    init_db()
    job1 = create_job(temporary_database, url="https://x.com/pl1", company="Stripe")
    job2 = create_job(temporary_database, url="https://x.com/pl2", company="Linear")
    create_application(job1, status="submitted")
    create_application(job2, status="interviews")

    result = await get_pipeline(context=make_test_context())
    assert "Submitted" in result or "submitted" in result.lower()
    assert "Interview" in result or "interview" in result.lower()


async def test_get_pipeline_shows_next_action(temporary_database):
    init_db()
    job = create_job(temporary_database, url="https://x.com/pl3")
    create_application(job, status="submitted", next_action="follow up em 2026-06-01")

    result = await get_pipeline(context=make_test_context())
    assert "follow up" in result


async def test_get_pipeline_skips_empty_statuses(temporary_database):
    init_db()
    job = create_job(temporary_database, url="https://x.com/pl4")
    create_application(job, status="submitted")

    result = await get_pipeline(context=make_test_context())
    # "Offer" section should not appear since no offer apps
    assert "## Offer" not in result


async def test_get_pipeline_shows_needs_review(temporary_database):
    init_db()
    job = create_job(temporary_database, url="https://x.com/pl-nr", company="Stripe")
    create_application(job, status="needs_review")

    result = await get_pipeline(context=make_test_context())
    assert "needs_review" in result.lower()


async def test_get_pipeline_total_count(temporary_database):
    """Total de candidaturas count reflects all Applications regardless of status."""
    init_db()
    job1 = create_job(temporary_database, url="https://x.com/pl-tc1")
    job2 = create_job(temporary_database, url="https://x.com/pl-tc2")
    job3 = create_job(temporary_database, url="https://x.com/pl-tc3")
    create_application(job1, status="submitted")
    create_application(job2, status="interviews")
    create_application(job3, status="rejected")

    result = await get_pipeline(context=make_test_context())
    assert "3" in result


async def test_get_pipeline_every_status_bucket_appears(temporary_database):
    """One application per status: every bucket header shows up, in the tool's declared order."""
    init_db()
    statuses = [
        "draft",
        "needs_review",
        "submitted",
        "screening",
        "interviews",
        "offer",
        "rejected",
    ]
    for index, status in enumerate(statuses):
        job = create_job(
            temporary_database, url=f"https://x.com/pl-all-{index}", company=f"Co{index}"
        )
        create_application(job, status=status)

    result = await get_pipeline(context=make_test_context())
    headers = [f"## {status.capitalize()} (1)" for status in statuses]
    positions = [result.index(header) for header in headers]
    # Headers appear in the declared status order, not e.g. insertion order.
    assert positions == sorted(positions)
    assert "**Total applications:** 7" in result


async def test_get_pipeline_multiple_applications_same_status_ordered_by_updated_at_desc(
    temporary_database,
):
    """Within a bucket, applications are ordered most-recently-updated first."""
    init_db()
    job_old = create_job(temporary_database, url="https://x.com/pl-ord1", company="OldCo")
    job_new = create_job(temporary_database, url="https://x.com/pl-ord2", company="NewCo")
    create_application(job_old, status="submitted")
    create_application(job_new, status="submitted")
    # Force NewCo's application to have a strictly later updated_at.

    app_new = Application.get(Application.job == job_new)
    app_new.updated_at = app_new.updated_at + timedelta(days=1)
    app_new.save()

    result = await get_pipeline(context=make_test_context())
    assert result.index("NewCo") < result.index("OldCo")


async def test_get_pipeline_no_applied_at_shows_dash(temporary_database):
    """An application without applied_at renders '—' instead of a date/crashing."""
    init_db()
    job = create_job(temporary_database, url="https://x.com/pl-noapplied")
    create_application(job, status="draft", applied_at=None)

    result = await get_pipeline(context=make_test_context())
    assert "(—)" in result


async def test_get_pipeline_shows_job_company_and_title(temporary_database):
    """Each pipeline row includes the job's id, company and title."""
    init_db()
    job = create_job(
        temporary_database, url="https://x.com/pl-fmt", company="Acme Corp", title="Backend Dev"
    )
    create_application(job, status="submitted")

    result = await get_pipeline(context=make_test_context())
    assert f"#{job.id} Acme Corp/Backend Dev" in result


async def test_get_pipeline_empty_has_zero_total_and_no_bucket_headers(temporary_database):
    """With zero applications, no '## Status' header appears anywhere, and total is 0."""
    init_db()

    result = await get_pipeline(context=make_test_context())
    assert "## " not in result
    assert "**Total applications:** 0" in result
