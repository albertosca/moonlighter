"""Unit tests for staleness detection — no real DB writes, no real network/browser."""

from unittest.mock import AsyncMock, MagicMock

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


async def test_linkedin_job_returns_404_is_stale(monkeypatch):
    job = _job(source="linkedin", company="linkedin", url="https://linkedin.com/jobs/1")
    page = AsyncMock()
    page.goto = AsyncMock(return_value=MagicMock(status=404))
    page.content = AsyncMock(return_value="<html></html>")
    page.close = AsyncMock()
    monkeypatch.setattr(
        "moonlighter.discovery.staleness.browser.new_page", AsyncMock(return_value=page)
    )
    result = await find_stale_jobs({("linkedin", "linkedin"): [job]}, {}, CONFIG)
    assert result.stale == [job]
    assert result.failed_companies == []


async def test_linkedin_job_closed_marker_in_page_is_stale(monkeypatch):
    job = _job(source="linkedin", company="linkedin", url="https://linkedin.com/jobs/1")
    page = AsyncMock()
    page.goto = AsyncMock(return_value=MagicMock(status=200))
    page.content = AsyncMock(return_value="<html>No longer accepting applications</html>")
    page.close = AsyncMock()
    monkeypatch.setattr(
        "moonlighter.discovery.staleness.browser.new_page", AsyncMock(return_value=page)
    )
    result = await find_stale_jobs({("linkedin", "linkedin"): [job]}, {}, CONFIG)
    assert result.stale == [job]


async def test_linkedin_job_still_open_is_not_stale(monkeypatch):
    job = _job(source="linkedin", company="linkedin", url="https://linkedin.com/jobs/1")
    page = AsyncMock()
    page.goto = AsyncMock(return_value=MagicMock(status=200))
    page.content = AsyncMock(return_value="<html>Apply now</html>")
    page.close = AsyncMock()
    monkeypatch.setattr(
        "moonlighter.discovery.staleness.browser.new_page", AsyncMock(return_value=page)
    )
    result = await find_stale_jobs({("linkedin", "linkedin"): [job]}, {}, CONFIG)
    assert result.stale == []


async def test_linkedin_browser_launch_failure_marks_failed(monkeypatch):
    job = _job(source="linkedin", company="linkedin", url="https://linkedin.com/jobs/1")
    monkeypatch.setattr(
        "moonlighter.discovery.staleness.browser.new_page",
        AsyncMock(side_effect=Exception("no browser")),
    )
    result = await find_stale_jobs({("linkedin", "linkedin"): [job]}, {}, CONFIG)
    assert result.stale == []
    assert result.failed_companies == ["linkedin"]


async def test_linkedin_goto_timeout_marks_failed(monkeypatch):
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    job = _job(source="linkedin", company="linkedin", url="https://linkedin.com/jobs/1")
    page = AsyncMock()
    page.goto = AsyncMock(side_effect=PlaywrightTimeout("timeout"))
    page.close = AsyncMock()
    monkeypatch.setattr(
        "moonlighter.discovery.staleness.browser.new_page", AsyncMock(return_value=page)
    )
    result = await find_stale_jobs({("linkedin", "linkedin"): [job]}, {}, CONFIG)
    assert result.stale == []
    assert result.failed_companies == ["linkedin"]


async def test_linkedin_goto_network_error_marks_failed_and_other_groups_continue(monkeypatch):
    """A non-timeout Playwright error (DNS failure, connection reset, net::ERR_*) must be
    caught too — it must not abort processing of other (source, company) groups."""
    from playwright.async_api import Error as PlaywrightError

    linkedin_job = _job(source="linkedin", company="linkedin", url="https://linkedin.com/jobs/1")
    greenhouse_job = _job(id=2, source="greenhouse", company="acme", url="https://x.com/1")
    page = AsyncMock()
    page.goto = AsyncMock(side_effect=PlaywrightError("net::ERR_CONNECTION_RESET"))
    page.close = AsyncMock()
    monkeypatch.setattr(
        "moonlighter.discovery.staleness.browser.new_page", AsyncMock(return_value=page)
    )
    scanners = {
        "greenhouse": _scanner(
            [RawJob(source="greenhouse", company="acme", title="Eng", url="https://x.com/1")]
        )
    }
    result = await find_stale_jobs(
        {
            ("linkedin", "linkedin"): [linkedin_job],
            ("greenhouse", "acme"): [greenhouse_job],
        },
        scanners,
        CONFIG,
    )
    assert result.failed_companies == ["linkedin"]
    assert result.stale == []


async def test_linkedin_multiple_failing_jobs_dedup_failed_companies(monkeypatch):
    """failed_companies must contain 'linkedin' at most once even if several jobs fail."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    job1 = _job(id=1, source="linkedin", company="linkedin", url="https://linkedin.com/jobs/1")
    job2 = _job(id=2, source="linkedin", company="linkedin", url="https://linkedin.com/jobs/2")
    page = AsyncMock()
    page.goto = AsyncMock(side_effect=PlaywrightTimeout("timeout"))
    page.close = AsyncMock()
    monkeypatch.setattr(
        "moonlighter.discovery.staleness.browser.new_page", AsyncMock(return_value=page)
    )
    result = await find_stale_jobs({("linkedin", "linkedin"): [job1, job2]}, {}, CONFIG)
    assert result.stale == []
    assert result.failed_companies == ["linkedin"]


async def test_linkedin_distinct_companies_reported_under_own_name(monkeypatch):
    """failed_companies must report the actual company per group, not a generic
    'linkedin' string — otherwise two distinct failing companies collapse into one
    indistinguishable entry."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    job_x = _job(id=1, source="linkedin", company="companyX", url="https://linkedin.com/jobs/1")
    job_y = _job(id=2, source="linkedin", company="companyY", url="https://linkedin.com/jobs/2")
    page = AsyncMock()
    page.goto = AsyncMock(side_effect=PlaywrightTimeout("timeout"))
    page.close = AsyncMock()
    monkeypatch.setattr(
        "moonlighter.discovery.staleness.browser.new_page", AsyncMock(return_value=page)
    )
    result = await find_stale_jobs(
        {
            ("linkedin", "companyX"): [job_x],
            ("linkedin", "companyY"): [job_y],
        },
        {},
        CONFIG,
    )
    assert result.stale == []
    assert set(result.failed_companies) == {"companyX", "companyY"}
    assert "linkedin" not in result.failed_companies


def test_staleness_result_defaults_to_empty_lists():
    result = StalenessResult()
    assert result.stale == []
    assert result.failed_companies == []
