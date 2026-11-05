"""scan_company scans one company, evaluates what is new and reports why not."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import ScanLog, init_db
from moonlighter.discovery.scan.results import render_scan_report
from moonlighter.discovery.scan.scanning import scan_company
from tests.discovery.fake_scan import make_raw_job

_fake_caller = MagicMock()


async def test_scan_company_rejects_unknown_source():
    report = render_scan_report(
        await scan_company(
            "workday", "acme", {"score_threshold": 6.5}, profile={}, caller=_fake_caller
        )
    )
    assert "Unknown source 'workday'" in report
    assert "greenhouse" in report  # names the valid ones


async def test_scan_company_scans_evaluates_and_reports(temporary_database):
    init_db()
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch(
            "moonlighter.discovery.scan.scanning.evaluate_and_store",
            new=AsyncMock(return_value=([], False)),
        ) as evaluate_mock,
    ):
        mock_greenhouse.return_value.scan = AsyncMock(
            return_value=[make_raw_job(1, source="greenhouse")]
        )
        report = render_scan_report(
            await scan_company(
                "greenhouse", "stripe", {"score_threshold": 6.5}, profile={}, caller=_fake_caller
            )
        )
    assert evaluate_mock.await_count == 1
    assert "company_list.yaml" in report  # the recurring-scan tip


async def test_scan_company_no_new_jobs_skips_evaluation(temporary_database):
    init_db()
    ScanLog.create(job_url="https://x.com/scan/1", source="greenhouse")
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch(
            "moonlighter.discovery.scan.scanning.evaluate_and_store", new=AsyncMock()
        ) as evaluate_mock,
    ):
        mock_greenhouse.return_value.scan = AsyncMock(
            return_value=[make_raw_job(1, source="greenhouse")]
        )
        report = render_scan_report(
            await scan_company(
                "greenhouse", "stripe", {"score_threshold": 6.5}, profile={}, caller=_fake_caller
            )
        )
    evaluate_mock.assert_not_called()
    assert "No new jobs at 'stripe'" in report
    assert "company_list.yaml" in report


async def test_scan_company_zero_raw_jobs_does_not_claim_all_already_known(temporary_database):
    """MINOR regression: an empty raw_jobs list can mean either 'company has no
    open postings' or 'the fetch failed' -- the old '(0 found, all already
    known)' message asserted the fetch succeeded and simply found nothing,
    which is false when it errored.
    """
    init_db()
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch(
            "moonlighter.discovery.scan.scanning.evaluate_and_store", new=AsyncMock()
        ) as evaluate_mock,
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=[])
        report = render_scan_report(
            await scan_company(
                "greenhouse", "stripe", {"score_threshold": 6.5}, profile={}, caller=_fake_caller
            )
        )
    evaluate_mock.assert_not_called()
    assert "No open jobs found at 'stripe'" in report
    assert "all already known" not in report
    assert "company_list.yaml" in report
