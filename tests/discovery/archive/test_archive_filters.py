"""archive_stale_jobs honours its filters, skips resolved jobs and ages out portal jobs."""

from datetime import datetime, timedelta

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.archive import archive_stale_jobs, format_archive_result
from moonlighter.discovery.staleness import StalenessResult
from tests.discovery.archive.stale_jobs import make_stale_job
from tests.discovery.fake_scan import CONFIG


async def test_archive_stale_jobs_filters_by_job_id(temporary_database, monkeypatch):
    init_db()
    target = make_stale_job(temporary_database, url="https://boards.greenhouse.io/acme/jobs/1")
    other = make_stale_job(temporary_database, url="https://boards.greenhouse.io/acme/jobs/2")

    seen_groups = []

    async def fake_find(jobs_by_company, scanners, config):
        seen_groups.append(jobs_by_company)
        return StalenessResult()

    monkeypatch.setattr("moonlighter.discovery.archive.find_stale_jobs", fake_find)
    await archive_stale_jobs(target.id, None, CONFIG)

    jobs_checked = seen_groups[0][("greenhouse", "acme")]
    assert [job.id for job in jobs_checked] == [target.id]
    assert other.id not in [job.id for job in jobs_checked]


async def test_archive_stale_jobs_filters_by_company_case_insensitive(
    temporary_database, monkeypatch
):
    init_db()
    acme_job = make_stale_job(temporary_database, company="acme", url="https://x.com/1")
    make_stale_job(temporary_database, company="beta", url="https://x.com/2")

    seen_groups = []

    async def fake_find(jobs_by_company, scanners, config):
        seen_groups.append(jobs_by_company)
        return StalenessResult()

    monkeypatch.setattr("moonlighter.discovery.archive.find_stale_jobs", fake_find)
    await archive_stale_jobs(None, "ACME", CONFIG)

    jobs_checked = seen_groups[0][("greenhouse", "acme")]
    assert [job.id for job in jobs_checked] == [acme_job.id]


async def test_archive_stale_jobs_excludes_resolved_statuses(temporary_database, monkeypatch):
    init_db()
    make_stale_job(temporary_database, status="applied", url="https://x.com/1")
    make_stale_job(temporary_database, status="rejected", url="https://x.com/2")
    make_stale_job(temporary_database, status="archived", url="https://x.com/3")

    seen_groups = []

    async def fake_find(jobs_by_company, scanners, config):
        seen_groups.append(jobs_by_company)
        return StalenessResult()

    monkeypatch.setattr("moonlighter.discovery.archive.find_stale_jobs", fake_find)
    await archive_stale_jobs(None, None, CONFIG)

    assert seen_groups[0] == {}


async def test_aged_portal_jobs_archive_as_aged_not_closed(temporary_database):
    init_db()
    old = Job.create(
        source="remoteok",
        company="acme",
        title="Eng",
        url="https://remoteok.com/j/1",
        status="new",
        found_at=datetime.now() - timedelta(days=45),  # noqa: DTZ005 - the database stores naive local time
    )
    result = await archive_stale_jobs(None, None, {"portal_max_age_days": 30})

    refreshed = Job.get_by_id(old.id)
    assert refreshed.status == "archived"  # aged out, NOT closed-at-source
    assert refreshed.closed_at is None
    assert result.aged == [{"company": "acme", "title": "Eng", "url": "https://remoteok.com/j/1"}]
    text = format_archive_result(result)
    assert "archived by age" in text
    assert "30" in text
