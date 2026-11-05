"""What scan_and_evaluate reports back after a run."""

from unittest.mock import AsyncMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.sources.base import RawJob
from moonlighter.mcp_tools.scanning import scan_and_evaluate

from tests._context import make_test_context
from tests.mcp_tools._records import batch_of, create_job, make_eval_result


async def test_scan_no_new_jobs(temporary_database):
    init_db()

    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
    ):
        for scanner_mock in (mock_greenhouse, mock_lever, mock_ashby):
            instance = AsyncMock()
            instance.scan = AsyncMock(return_value=[])
            scanner_mock.return_value = instance
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(context=make_test_context())
    assert "No new jobs found" in result


async def test_scan_and_evaluate_reports_archived_stale_jobs(temporary_database):
    init_db()

    # Pre-existing eligible job whose company listing will come back empty → stale.
    create_job(
        temporary_database,
        url="https://boards.greenhouse.io/stale-co/jobs/1",
        company="stale-co",
        status="new",
    )

    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
    ):
        for scanner_mock in (mock_greenhouse, mock_lever, mock_ashby):
            instance = AsyncMock()
            instance.scan = AsyncMock(return_value=[])
            scanner_mock.return_value = instance
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(context=make_test_context())

    assert "archived" in result.lower()
    job = Job.get(Job.url == "https://boards.greenhouse.io/stale-co/jobs/1")
    assert job.status == "archived"
    assert job.closed_at is not None


async def test_scan_and_evaluate_no_new_jobs_still_runs_archive_check(temporary_database):
    """Regression: the 'no new jobs' early-exit message must still show the archive section."""
    init_db()

    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
    ):
        for scanner_mock in (mock_greenhouse, mock_lever, mock_ashby):
            instance = AsyncMock()
            instance.scan = AsyncMock(return_value=[])
            scanner_mock.return_value = instance
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(context=make_test_context())

    assert "No new jobs found" in result
    assert "No closed jobs found." in result


async def test_scan_all_below_threshold(temporary_database):
    init_db()

    raw = RawJob(
        source="greenhouse",
        company="co",
        title="Eng",
        url="https://x.com/1",
        description="A detailed job description that goes on.",
    )
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.scan.pipeline.evaluate_jobs_batch",
            new=batch_of(make_eval_result(score=4.0)),
        ),
        patch(
            "moonlighter.discovery.scan.scanning.load_company_list",
            return_value={"greenhouse": ["co"]},
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=[raw])
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(context=make_test_context())
    assert "threshold" in result.lower()
    # Job should be archived because score=4.0 is below the default threshold=6.5
    job = Job.get(Job.url == "https://x.com/1")
    assert job.status == "archived"


async def test_scan_above_threshold_shows_table(temporary_database):
    init_db()

    raw = RawJob(
        source="greenhouse",
        company="Stripe",
        title="Sr Eng",
        url="https://x.com/2",
        description="A detailed job description that goes on.",
    )
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.scan.pipeline.evaluate_jobs_batch",
            new=batch_of(make_eval_result(score=8.0)),
        ),
        patch(
            "moonlighter.discovery.scan.scanning.load_company_list",
            return_value={"greenhouse": ["stripe"]},
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=[raw])
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(context=make_test_context())
    assert "Stripe" in result
    assert "Sr Eng" in result
