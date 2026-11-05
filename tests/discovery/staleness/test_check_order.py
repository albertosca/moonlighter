"""The order find_stale_jobs tries a source's checks in, and what it reports last."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from moonlighter.discovery.sources.base import RawJob
from moonlighter.discovery.staleness import find_stale_jobs

from tests.discovery.staleness.fake_jobs import CHECKERS, CONFIG, make_job, make_scanner


async def test_a_listing_source_is_checked_by_its_listing_before_any_checker_plugin():
    job = make_job(source="greenhouse", url="https://x.com/1")
    plugin = AsyncMock()
    scanners = {
        "greenhouse": make_scanner(
            [RawJob(source="greenhouse", company="acme", title="Eng", url="https://x.com/1")]
        )
    }
    with patch(CHECKERS, return_value={"greenhouse": plugin}):
        result = await find_stale_jobs({("greenhouse", "acme"): [job]}, scanners, CONFIG)
    plugin.assert_not_called()
    scanners["greenhouse"].scan.assert_awaited_once()
    assert result.stale == []


async def test_a_portal_source_is_tallied_before_any_checker_plugin():
    job = make_job(source="remoteok", company="acme")
    plugin = AsyncMock()
    with patch(CHECKERS, return_value={"remoteok": plugin}):
        result = await find_stale_jobs({("remoteok", "acme"): [job]}, {}, CONFIG)
    plugin.assert_not_called()
    assert result.failed_companies == ["1 remoteok job(s) (portal feed, no per-company listing)"]


async def test_a_listing_source_without_a_scanner_raises_key_error():
    job = make_job(source="greenhouse")
    with pytest.raises(KeyError, match="greenhouse"):
        await find_stale_jobs({("greenhouse", "acme"): [job]}, {}, CONFIG)


async def test_portal_lines_come_after_every_company_in_source_order():
    failing = make_scanner("not a list")
    jobs_by_company = {
        ("remoteok", "a"): [make_job(1, source="remoteok")],
        ("greenhouse", "acme"): [make_job(2)],
        ("weworkremotely", "b"): [make_job(3, source="weworkremotely")],
        ("remotive", "c"): [make_job(4, source="remotive")],
        ("remoteok", "d"): [make_job(5, source="remoteok")],
    }
    result = await find_stale_jobs(jobs_by_company, {"greenhouse": failing}, CONFIG)
    assert result.failed_companies == [
        "acme",
        "2 remoteok job(s) (portal feed, no per-company listing)",
        "1 remotive job(s) (portal feed, no per-company listing)",
        "1 weworkremotely job(s) (portal feed, no per-company listing)",
    ]


async def test_stale_by_age_keeps_the_order_the_companies_were_given_in():
    old_first = make_job(1, source="remoteok", company="a")
    old_second = make_job(2, source="remotive", company="b")
    for job in (old_first, old_second):
        job.found_at = datetime.now() - timedelta(days=90)  # noqa: DTZ005 - the database stores naive local time
    jobs_by_company = {("remotive", "b"): [old_second], ("remoteok", "a"): [old_first]}
    result = await find_stale_jobs(jobs_by_company, {}, {"portal_max_age_days": 30})
    assert result.stale_by_age == [old_second, old_first]
    assert result.failed_companies == []


async def test_failed_companies_is_deduplicated_only_on_the_checker_path():
    scanner = make_scanner("not a list")
    jobs_by_company = {
        ("greenhouse", "acme"): [make_job(1, source="greenhouse")],
        ("lever", "acme"): [make_job(2, source="lever")],
    }
    result = await find_stale_jobs(
        jobs_by_company, {"greenhouse": scanner, "lever": scanner}, CONFIG
    )
    assert result.failed_companies == ["acme", "acme"]
