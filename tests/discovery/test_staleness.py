"""Unit tests for staleness detection — no real DB writes, no real network/browser."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.discovery.sources.base import RawJob
from moonlighter.discovery.staleness import StalenessResult, find_stale_jobs

CONFIG: dict = {}


def _job(id=1, source="greenhouse", company="acme", url="https://x.com/1", title="Eng"):
    job = MagicMock()
    job.id = id
    job.source = source
    job.company = company
    job.url = url
    job.title = title
    return job


def _scanner(return_value):
    scanner = MagicMock()
    scanner.scan = AsyncMock(return_value=return_value)
    return scanner


async def test_job_still_in_listing_is_not_stale():
    job = _job(url="https://x.com/1")
    scanners = {
        "greenhouse": _scanner(
            [RawJob(source="greenhouse", company="acme", title="Eng", url="https://x.com/1")]
        )
    }
    result = await find_stale_jobs({("greenhouse", "acme"): [job]}, scanners, CONFIG)
    assert result.stale == []
    assert result.failed_companies == []


async def test_job_missing_from_listing_is_stale():
    job = _job(url="https://x.com/1")
    scanners = {"greenhouse": _scanner([])}  # company has zero open postings now
    result = await find_stale_jobs({("greenhouse", "acme"): [job]}, scanners, CONFIG)
    assert result.stale == [job]
    assert result.failed_companies == []


async def test_scanner_exception_marks_company_failed_not_stale():
    """A transient failure must never be treated as 'zero open jobs' — fail-safe."""
    job = _job(url="https://x.com/1")
    scanner = MagicMock()
    scanner.scan = AsyncMock(side_effect=Exception("timeout"))
    result = await find_stale_jobs({("greenhouse", "acme"): [job]}, {"greenhouse": scanner}, CONFIG)
    assert result.stale == []
    assert result.failed_companies == ["acme"]


async def test_scanner_malformed_response_marks_company_failed():
    job = _job(url="https://x.com/1")
    scanners = {"greenhouse": _scanner("not a list")}
    result = await find_stale_jobs({("greenhouse", "acme"): [job]}, scanners, CONFIG)
    assert result.stale == []
    assert result.failed_companies == ["acme"]


async def test_unsupported_source_marks_company_failed():
    job = _job(source="manual", company="somewhere", url="https://x.com/1")
    result = await find_stale_jobs({("manual", "somewhere"): [job]}, {}, CONFIG)
    assert result.stale == []
    assert result.failed_companies == ["somewhere (source 'manual' has no listing check)"]


async def test_registered_checker_plugin_is_called_for_its_source():
    """A source with no listing support (e.g. LinkedIn) can be handled by a
    checker registered via the moonlighter.staleness_checkers entry_points
    group — see docs/superpowers/specs/2026-07-22-linkedin-plugin-split-design.md.
    Never hardcoded by source name here: any plugin-registered source works."""
    job = _job(source="acme_ats", company="acme", url="https://acme-ats.example/jobs/1")
    fake_checker = AsyncMock()
    with patch(
        "moonlighter.discovery.staleness.discover_entry_points_by_name",
        return_value={"acme_ats": fake_checker},
    ):
        result = await find_stale_jobs({("acme_ats", "acme"): [job]}, {}, CONFIG)
    fake_checker.assert_called_once_with("acme", [job], CONFIG, result)
    assert result.failed_companies == []


async def test_no_registered_checker_falls_through_to_no_listing_check():
    """Same as test_unsupported_source_marks_company_failed but explicit about
    the "no plugin installed for this source" case — the steady state for the
    public repo alone, with no private checker plugin present."""
    job = _job(source="acme_ats", company="acme", url="https://acme-ats.example/jobs/1")
    with patch("moonlighter.discovery.staleness.discover_entry_points_by_name", return_value={}):
        result = await find_stale_jobs({("acme_ats", "acme"): [job]}, {}, CONFIG)
    assert result.stale == []
    assert result.failed_companies == ["acme (source 'acme_ats' has no listing check)"]


async def test_checker_plugin_exception_marks_company_failed_not_stale():
    """An unguarded exception from a (untrusted, plugin-provided) checker must not
    propagate out of find_stale_jobs — it's caught the same way a first-party
    listing-scanner failure is, and must not abort other (source, company) groups."""
    failing_job = _job(source="acme_ats", company="acme", url="https://acme-ats.example/jobs/1")
    greenhouse_job = _job(id=2, source="greenhouse", company="stripe", url="https://x.com/1")
    fake_checker = AsyncMock(side_effect=Exception("boom"))
    scanners = {
        "greenhouse": _scanner(
            [RawJob(source="greenhouse", company="stripe", title="Eng", url="https://x.com/1")]
        )
    }
    with patch(
        "moonlighter.discovery.staleness.discover_entry_points_by_name",
        return_value={"acme_ats": fake_checker},
    ):
        result = await find_stale_jobs(
            {
                ("acme_ats", "acme"): [failing_job],
                ("greenhouse", "stripe"): [greenhouse_job],
            },
            scanners,
            CONFIG,
        )
    assert result.stale == []
    assert result.failed_companies == ["acme"]


async def test_checker_plugin_exception_after_partial_failure_does_not_duplicate():
    """If a checker already added the company to failed_companies before raising
    (e.g. a partial per-job failure inside the checker itself, as the real
    LinkedIn checker's own per-job try/except does), the dispatcher's own guard
    must not add it a second time."""
    job = _job(source="acme_ats", company="acme", url="https://acme-ats.example/jobs/1")

    async def flaky_checker(company, jobs, config, result):
        result.failed_companies.append(company)
        raise Exception("boom after partial failure")

    with patch(
        "moonlighter.discovery.staleness.discover_entry_points_by_name",
        return_value={"acme_ats": flaky_checker},
    ):
        result = await find_stale_jobs({("acme_ats", "acme"): [job]}, {}, CONFIG)
    assert result.failed_companies == ["acme"]


def test_staleness_result_defaults_to_empty_lists():
    result = StalenessResult()
    assert result.stale == []
    assert result.failed_companies == []


async def test_portal_jobs_aggregate_into_one_line_per_source():
    """Portal boards aren't per-company: re-listing "the company" isn't possible,
    so staleness reports one aggregate line per source instead of flooding
    failed_companies with one entry per job's (made-up) company."""
    jobs_by_company = {
        ("remoteok", "acme"): [_job(1)],
        ("remoteok", "globex"): [_job(2), _job(3)],
    }
    result = await find_stale_jobs(jobs_by_company, {}, {})
    assert result.failed_companies == ["3 remoteok job(s) (portal feed, no per-company listing)"]
