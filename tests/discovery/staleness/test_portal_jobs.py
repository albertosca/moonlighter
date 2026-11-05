"""Portal jobs: one aggregate line per source, and age as the only closing signal."""

from datetime import datetime, timedelta

from moonlighter.discovery.staleness import find_stale_jobs
from tests.discovery.staleness.fake_jobs import make_job

PORTAL_LINE = "{count} remoteok job(s) (portal feed, no per-company listing)"


async def test_portal_jobs_aggregate_into_one_line_per_source():
    """Portal boards aren't per-company: re-listing "the company" isn't possible.

    Staleness reports one aggregate line per source instead of flooding failed_companies with
    one entry per job's (made-up) company.
    """
    jobs_by_company = {
        ("remoteok", "acme"): [make_job(1)],
        ("remoteok", "globex"): [make_job(2), make_job(3)],
    }
    result = await find_stale_jobs(jobs_by_company, {}, {})
    assert result.failed_companies == [PORTAL_LINE.format(count=3)]


async def test_portal_jobs_older_than_the_age_limit_go_stale_by_age():
    """A portal job can never be staleness-checked at its source, so age is the only signal.

    Older than portal_max_age_days -> stale_by_age; younger stays in the aggregate
    can't-check note.
    """
    old = make_job(1)
    old.found_at = datetime.now() - timedelta(days=45)  # noqa: DTZ005 - the database stores naive local time
    young = make_job(2)
    young.found_at = datetime.now() - timedelta(days=3)  # noqa: DTZ005 - the database stores naive local time
    jobs_by_company = {("remoteok", "acme"): [old, young]}

    result = await find_stale_jobs(jobs_by_company, {}, {"portal_max_age_days": 30})

    assert result.stale_by_age == [old]
    assert result.failed_companies == [PORTAL_LINE.format(count=1)]


async def test_portal_age_archiving_disabled_with_zero():
    old = make_job(1)
    old.found_at = datetime.now() - timedelta(days=400)  # noqa: DTZ005 - the database stores naive local time
    result = await find_stale_jobs({("remoteok", "acme"): [old]}, {}, {"portal_max_age_days": 0})
    assert result.stale_by_age == []
    assert result.failed_companies == [PORTAL_LINE.format(count=1)]
