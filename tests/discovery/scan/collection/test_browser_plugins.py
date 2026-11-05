"""Browser-scanner plugins add jobs, or a warning, but never block the other sources."""

from unittest.mock import AsyncMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.scan.collection import _run_browser_scanner
from moonlighter.discovery.sources.base import RawJob, ScannerSessionExpiredError
from tests.discovery.fake_scan import CONFIG, FakeBrowserScanner, make_raw_job, run_scan


async def test_run_browser_scanner_browser_launch_failure_is_silent():
    """If browser.new_page() itself raises (no browser configured, launch error),
    the browser-scanner plugin is skipped silently -- same as any other failure,
    it must not block the HTTP results.
    """
    with patch("moonlighter.core.browser", create=True) as mock_browser:
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        jobs, warning = await _run_browser_scanner(FakeBrowserScanner, "engineer", CONFIG)
    assert jobs == []
    assert warning is None


async def test_scan_linkedin_jobs_are_evaluated(temporary_database):
    init_db()
    li_raw = RawJob(
        source="linkedin",
        company="LinkedInCo",
        title="Engineer",
        url="https://x.com/li/1",
        description="A detailed job description that goes on.",
    )
    result = await run_scan([], linkedin_jobs=[li_raw])
    assert Job.get(Job.url == "https://x.com/li/1").company == "LinkedInCo"
    assert "LinkedInCo" in result


async def test_scan_registered_scanner_session_expired_adds_warning(temporary_database):
    init_db()
    result = await run_scan(
        [make_raw_job(2)], linkedin_error=ScannerSessionExpiredError("session expired")
    )
    assert "⚠️  FakeBrowser: session expired" in result


async def test_scan_registered_scanner_generic_error_is_swallowed(temporary_database):
    init_db()
    result = await run_scan([make_raw_job(3)], linkedin_error=RuntimeError("boom"))
    # a generic scanner error doesn't become a warning nor block the HTTP results
    assert "FakeBrowser" not in result
    assert Job.get(Job.url == "https://x.com/scan/3").status == "new"
