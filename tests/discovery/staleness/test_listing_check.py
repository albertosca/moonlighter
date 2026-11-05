"""Staleness of a job whose source can be re-listed: present, gone, or the check failed."""

from unittest.mock import AsyncMock, MagicMock

from moonlighter.discovery.sources.base import RawJob
from moonlighter.discovery.staleness import StalenessResult, find_stale_jobs
from tests.discovery.staleness.fake_jobs import CONFIG, make_job, make_scanner


async def test_job_still_in_listing_is_not_stale():
    job = make_job(url="https://x.com/1")
    scanners = {
        "greenhouse": make_scanner(
            [RawJob(source="greenhouse", company="acme", title="Eng", url="https://x.com/1")]
        )
    }
    result = await find_stale_jobs({("greenhouse", "acme"): [job]}, scanners, CONFIG)
    assert result.stale == []
    assert result.failed_companies == []


async def test_stored_normalized_url_matches_raw_apply_suffix_in_listing():
    """CRITICAL regression: stored job.url is normalized, the listing's is not.

    `normalize_job_url` strips the Recruitee /c/new apply suffix from the stored url, but the fresh
    listing still returns the raw careers_apply_url ending in /c/new. Comparing the two forms
    unnormalized would archive every freshly-stored Recruitee job as stale on its first
    re-scan — both sides must be normalized before comparing.
    """
    job = make_job(source="recruitee", company="x", url="https://x.recruitee.com/o/dev")
    scanners = {
        "recruitee": make_scanner(
            [
                RawJob(
                    source="recruitee",
                    company="x",
                    title="Dev",
                    url="https://x.recruitee.com/o/dev/c/new",
                )
            ]
        )
    }
    result = await find_stale_jobs({("recruitee", "x"): [job]}, scanners, CONFIG)
    assert result.stale == []
    assert result.failed_companies == []


async def test_job_missing_from_listing_is_stale():
    job = make_job(url="https://x.com/1")
    scanners = {"greenhouse": make_scanner([])}  # company has zero open postings now
    result = await find_stale_jobs({("greenhouse", "acme"): [job]}, scanners, CONFIG)
    assert result.stale == [job]
    assert result.failed_companies == []


async def test_scanner_exception_marks_company_failed_not_stale():
    """A transient failure must never be treated as 'zero open jobs' — fail-safe."""
    job = make_job(url="https://x.com/1")
    scanner = MagicMock()
    scanner.scan = AsyncMock(side_effect=RuntimeError("timeout"))
    result = await find_stale_jobs({("greenhouse", "acme"): [job]}, {"greenhouse": scanner}, CONFIG)
    assert result.stale == []
    assert result.failed_companies == ["acme"]


async def test_scanner_malformed_response_marks_company_failed():
    job = make_job(url="https://x.com/1")
    scanners = {"greenhouse": make_scanner("not a list")}
    result = await find_stale_jobs({("greenhouse", "acme"): [job]}, scanners, CONFIG)
    assert result.stale == []
    assert result.failed_companies == ["acme"]


def test_staleness_result_defaults_to_empty_lists():
    result = StalenessResult()
    assert result.stale == []
    assert result.failed_companies == []
