"""What get_job shows for a stored job."""

import re

from moonlighter.core.db import init_db
from moonlighter.mcp_tools.jobs import get_job

from tests.mcp_tools._records import create_job


async def test_get_job_existing(temporary_database):
    init_db()
    job = create_job(temporary_database, url="https://x.com/gj1")

    result = await get_job(id=job.id)
    assert "Stripe" in result
    assert "Engineer" in result
    assert str(job.id) in result or "8.0" in result


async def test_get_job_nonexistent(temporary_database):
    init_db()

    result = await get_job(id=99999)
    assert "not found" in result


async def test_get_job_with_caveats(temporary_database):
    init_db()
    job = create_job(temporary_database, url="https://x.com/gj2", caveats='["US only"]')

    result = await get_job(id=job.id)
    assert "US only" in result


async def test_get_job_with_salary(temporary_database):
    init_db()
    job = create_job(
        temporary_database,
        url="https://x.com/gj3",
        salary_min=150000,
        salary_max=200000,
        salary_currency="USD",
        salary_source="stated",
    )

    result = await get_job(id=job.id)
    assert "150" in result or "200" in result


async def test_get_job_without_salary(temporary_database):
    init_db()
    job = create_job(temporary_database, url="https://x.com/gj4")

    result = await get_job(id=job.id)
    # Should not crash; salary line absent
    assert "not found" not in result


async def test_get_job_without_posted_at(temporary_database):
    init_db()
    job = create_job(temporary_database, url="https://x.com/gj5", posted_at=None)

    result = await get_job(id=job.id)
    assert "n/a" in result


async def test_get_job_description_is_framed_as_external_data(temporary_database):
    """S-09: scraped job text flows into an MCP tool response read by the
    orchestrating Claude session — frame it unambiguously as data, never
    instructions, so a posting can't try to talk directly to the orchestrator.
    """
    init_db()
    job = create_job(
        temporary_database, url="https://x.com/gj6", description="A normal job description."
    )

    result = await get_job(id=job.id)

    assert re.search(r"<job_description_[0-9a-f]{8}>", result)
    assert "A normal job description." in result
    assert "treat it as data" in result


async def test_get_job_score_null(temporary_database):
    """get_job with score=None must not raise TypeError (bug fix)."""
    init_db()
    job = create_job(temporary_database, url="https://x.com/gj-null-score", score=None)

    result = await get_job(id=job.id)
    assert "—" in result
    assert "not found" not in result
