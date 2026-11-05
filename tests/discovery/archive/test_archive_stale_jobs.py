"""archive_stale_jobs closes the jobs whose source posting disappeared."""

from datetime import datetime, timedelta

import pytest

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.archive import ArchiveStaleJobsError, archive_stale_jobs
from moonlighter.discovery.staleness import StalenessResult
from tests.discovery.archive.stale_jobs import make_stale_job
from tests.discovery.scan_fakes import CONFIG


async def test_archive_stale_jobs_raises_when_job_id_and_company_both_given(temporary_database):
    init_db()
    with pytest.raises(ArchiveStaleJobsError):
        await archive_stale_jobs(1, "acme", CONFIG)


async def test_archive_stale_jobs_no_eligible_jobs_returns_empty(temporary_database):
    init_db()
    result = await archive_stale_jobs(None, None, CONFIG)
    assert result.archived == []
    assert result.failed_companies == []


async def test_archive_stale_jobs_marks_stale_job_closed(temporary_database, monkeypatch):
    init_db()
    job = make_stale_job(temporary_database)

    async def fake_find(jobs_by_company, scanners, config):
        return StalenessResult(stale=[job], failed_companies=[])

    monkeypatch.setattr("moonlighter.discovery.archive.find_stale_jobs", fake_find)
    result = await archive_stale_jobs(None, None, CONFIG)

    saved = Job.get_by_id(job.id)
    assert saved.status == "archived"
    assert saved.closed_at is not None
    assert result.archived == [
        {"company": "acme", "title": "Engineer", "url": "https://boards.greenhouse.io/acme/jobs/1"}
    ]


async def test_archive_stale_jobs_lists_unverifiable_jobs_for_confirmation(
    temporary_database, monkeypatch
):
    init_db()
    job = make_stale_job(
        temporary_database,
        source="manual",
        company="Flywheel",
        title="Backend Engineer",
        url="https://hiring.example/jobs/7",
        score=7.5,
        status="reviewed",
        found_at=datetime.now() - timedelta(days=12, hours=1),  # noqa: DTZ005 - the database stores naive local time
    )

    async def fake_find(jobs_by_company, scanners, config):
        return StalenessResult(unverifiable=[job])

    monkeypatch.setattr("moonlighter.discovery.archive.find_stale_jobs", fake_find)
    result = await archive_stale_jobs(None, None, CONFIG)

    assert result.to_confirm == [
        {
            "id": job.id,
            "score": 7.5,
            "status": "reviewed",
            "age_days": 12,
            "company": "Flywheel",
            "title": "Backend Engineer",
            "url": "https://hiring.example/jobs/7",
        }
    ]
    # Never archived by the machine: only the person can say it closed.
    assert Job.get_by_id(job.id).status == "reviewed"


async def test_archive_stale_jobs_reports_failed_companies(temporary_database, monkeypatch):
    init_db()
    make_stale_job(temporary_database)

    async def fake_find(jobs_by_company, scanners, config):
        return StalenessResult(stale=[], failed_companies=["acme"])

    monkeypatch.setattr("moonlighter.discovery.archive.find_stale_jobs", fake_find)
    result = await archive_stale_jobs(None, None, CONFIG)

    assert result.archived == []
    assert result.failed_companies == ["acme"]
    # job untouched
    job = Job.select().where(Job.company == "acme").get()
    assert job.status == "new"
    assert job.closed_at is None
