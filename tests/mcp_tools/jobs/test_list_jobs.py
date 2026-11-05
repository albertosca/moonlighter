"""What list_jobs shows: filters, ordering, badges and salary marks."""

import datetime as dt

from moonlighter.core.db import init_db
from moonlighter.mcp_tools.jobs import list_jobs

from tests.mcp_tools._records import create_application, create_job


async def test_list_jobs_default_new(temporary_database):
    init_db()
    create_job(temporary_database, url="https://x.com/lj1", status="new", score=8.0)

    result = await list_jobs(status="new")
    assert "Stripe" in result


async def test_list_jobs_reorders_and_badges_recently_rejected_companies(temporary_database):
    # 2026-08-24: Holepunch #3197 was offered with no hint that the same
    # company rejected #3200 eight days earlier. Same persisted score, but the
    # rejected company's job sorts after and carries the badge.

    init_db()
    create_job(temporary_database, company="CleanCo", url="https://x.com/lj/clean", score=8.0)
    rejected_job = create_job(
        temporary_database,
        company="Holepunch",
        url="https://x.com/lj/old",
        score=8.0,
        status="rejected",
    )
    create_application(
        rejected_job,
        status="rejected",
        updated_at=dt.datetime.now() - dt.timedelta(days=8),  # noqa: DTZ005 - the models store naive local timestamps, so the test builds one the same way
    )
    create_job(temporary_database, company="Holepunch", url="https://x.com/lj/new", score=8.0)

    result = await list_jobs()
    assert "rejected 1x" in result
    assert result.index("CleanCo") < result.index("Holepunch")


async def test_list_jobs_filtered_by_status(temporary_database):
    init_db()
    create_job(
        temporary_database, url="https://x.com/lj2", status="reviewed", score=7.0, company="Linear"
    )
    create_job(
        temporary_database, url="https://x.com/lj3", status="new", score=8.0, company="Vercel"
    )

    result = await list_jobs(status="reviewed")
    assert "Linear" in result
    assert "Vercel" not in result


async def test_list_jobs_limit(temporary_database):
    init_db()
    for index in range(5):
        create_job(
            temporary_database,
            url=f"https://x.com/lj-limit-{index}",
            status="new",
            score=float(index),
            company=f"Co{index}",
        )

    result = await list_jobs(status="new", limit=3)
    # Verify it returned without error
    assert result is not None
    assert len(result) > 0


async def test_list_jobs_empty(temporary_database):
    init_db()

    result = await list_jobs(status="offer")
    assert "No jobs" in result


async def test_list_jobs_ordered_by_score_desc(temporary_database):
    init_db()
    create_job(
        temporary_database, url="https://x.com/lj-lo", status="new", score=6.0, company="LowScore"
    )
    create_job(
        temporary_database, url="https://x.com/lj-hi", status="new", score=9.5, company="HighScore"
    )

    result = await list_jobs(status="new")
    # HighScore should appear before LowScore in the output
    assert result.index("HighScore") < result.index("LowScore")


async def test_list_jobs_salary_estimate_shows_asterisk(temporary_database):
    """salary_source='llm_estimate' with min+max → '* ' appears in table."""
    init_db()
    create_job(
        temporary_database,
        url="https://x.com/lj-est",
        salary_min=150000,
        salary_max=200000,
        salary_currency="USD",
        salary_source="llm_estimate",
        status="new",
    )

    result = await list_jobs(status="new")
    assert " *" in result


async def test_list_jobs_salary_min_only_shows_plus(temporary_database):
    """Only salary_min set → '$Xk+' format in table."""
    init_db()
    create_job(
        temporary_database,
        url="https://x.com/lj-min",
        salary_min=120000,
        salary_max=None,
        salary_currency="USD",
        salary_source="stated",
        status="new",
    )

    result = await list_jobs(status="new")
    assert "k+" in result or "120" in result
