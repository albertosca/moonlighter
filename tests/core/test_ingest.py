from unittest.mock import AsyncMock, patch

from moonlighter.core.db import Job, ScanLog, init_db
from moonlighter.core.posting import FetchedPosting


async def test_job_from_url_returns_the_existing_job_without_fetching(tmp_db):
    from moonlighter.core.ingest import job_from_url

    init_db()
    existing = Job.create(
        source="greenhouse",
        company="Acme",
        title="Eng",
        url="https://boards.greenhouse.io/acme/jobs/1",
        status="new",
    )
    with patch(
        "moonlighter.core.ingest.fetch_posting_via_ats", side_effect=AssertionError("no fetch")
    ):
        job = await job_from_url("https://boards.greenhouse.io/acme/jobs/1/")
    assert job is not None and job.id == existing.id


async def test_job_from_url_ingests_via_the_ats_api_unscored(tmp_db):
    from moonlighter.core.ingest import job_from_url

    init_db()
    posting = FetchedPosting(
        company="Acme", title="Staff Engineer", description="A long description of the role."
    )
    with patch(
        "moonlighter.core.ingest.fetch_posting_via_ats", new=AsyncMock(return_value=posting)
    ):
        job = await job_from_url("https://boards.greenhouse.io/acme/jobs/7")
    assert job is not None
    assert (job.company, job.title, job.source, job.status, job.score) == (
        "Acme",
        "Staff Engineer",
        "manual",
        "needs_review",
        None,
    )
    assert job.score_notes == "ingested by URL for a sheet — not evaluated"
    assert ScanLog.select().where(ScanLog.job_url == job.url).exists()  # a later scan dedups it


async def test_job_from_url_falls_back_to_the_generic_fetch_for_the_description(tmp_db):
    from moonlighter.core.ingest import job_from_url

    init_db()
    posting = FetchedPosting(company="Acme", title="Staff Engineer", description=None)
    with (
        patch("moonlighter.core.ingest.fetch_posting_via_ats", new=AsyncMock(return_value=posting)),
        patch(
            "moonlighter.core.ingest.fetch_description",
            new=AsyncMock(return_value=("Generic text", None)),
        ),
    ):
        job = await job_from_url("https://boards.greenhouse.io/acme/jobs/8")
    assert job is not None and job.description == "Generic text"


async def test_job_from_url_is_none_when_the_posting_cannot_be_named(tmp_db):
    # No ATS match and no overrides: the page cannot name itself, so the
    # generic fetch (an HTTP request) must never run -- a Job row with empty
    # company would poison list_jobs and the sheet header anyway.
    from moonlighter.core.ingest import job_from_url

    init_db()
    with (
        patch("moonlighter.core.ingest.fetch_posting_via_ats", new=AsyncMock(return_value=None)),
        patch(
            "moonlighter.core.ingest.fetch_description",
            side_effect=AssertionError("no fetch"),
        ),
    ):
        assert await job_from_url("https://example.com/careers/123") is None
    assert Job.select().count() == 0


async def test_job_from_url_with_overrides_ingests_a_non_ats_page(tmp_db):
    # No ATS match, but --company/--title supplied: the page can now be
    # named, so the generic fetch runs to supply the description.
    from moonlighter.core.ingest import job_from_url

    init_db()
    with (
        patch("moonlighter.core.ingest.fetch_posting_via_ats", new=AsyncMock(return_value=None)),
        patch(
            "moonlighter.core.ingest.fetch_description",
            new=AsyncMock(return_value=("Page text", None)),
        ),
    ):
        job = await job_from_url(
            "https://example.com/careers/123", company="Acme", title="Staff Eng"
        )
    assert job is not None
    assert (job.company, job.title, job.description) == ("Acme", "Staff Eng", "Page text")


async def test_job_from_url_is_none_when_the_fetch_fails(tmp_db):
    from moonlighter.core.ingest import job_from_url

    init_db()
    posting = FetchedPosting(company="Acme", title="Eng", description=None)
    with (
        patch("moonlighter.core.ingest.fetch_posting_via_ats", new=AsyncMock(return_value=posting)),
        patch(
            "moonlighter.core.ingest.fetch_description",
            new=AsyncMock(return_value=(None, "HTTP 404")),
        ),
    ):
        assert await job_from_url("https://boards.greenhouse.io/acme/jobs/9") is None
