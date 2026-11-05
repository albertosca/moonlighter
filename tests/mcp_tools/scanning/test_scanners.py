"""A scanner that fails or loses its session never blocks the others."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import init_db
from moonlighter.discovery.sources.base import RawJob, ScannerSessionExpiredError
from moonlighter.mcp_tools.scanning import scan_and_evaluate

from tests._context import make_test_context
from tests.mcp_tools._records import batch_of, make_eval_result


def make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/1"):
    page = MagicMock()
    page.url = url
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.close = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_selector = AsyncMock()
    return page


class _FakeSessionExpiredSource:
    def __init__(self, page: Any) -> None:
        pass

    async def scan(self, **keyword_arguments: Any) -> list[Any]:
        raise ScannerSessionExpiredError("Session expired.")


async def test_scan_linkedin_failure_doesnt_block(temporary_database):
    init_db()

    raw = RawJob(
        source="greenhouse",
        company="co",
        title="Eng",
        url="https://x.com/4",
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
            return_value={"greenhouse": ["co"]},
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=[raw])
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("LinkedIn not available"))
        result = await scan_and_evaluate(context=make_test_context())
    # LinkedIn failure doesn't block the HTTP results; job with score=8.0 above the threshold.
    assert "co" in result or "Eng" in result or "jobs" in result.lower()


async def test_scan_registered_scanner_session_expired_shows_warning(temporary_database):
    """A registered browser-scanner plugin raising ScannerSessionExpiredError ->
    explicit warning in the result (no silence).
    """
    init_db()

    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.scan.collection.discover_entry_points",
            return_value=[_FakeSessionExpiredSource],
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=[])
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(return_value=make_mock_page())
        result = await scan_and_evaluate(context=make_test_context())

    assert "⚠️  _FakeSessionExpiredSource: Session expired." in result
    assert "expired" in result or "login" in result.lower()


async def test_scan_registered_scanner_session_expired_does_not_block_http_results(
    temporary_database,
):
    """A registered browser-scanner plugin's ScannerSessionExpiredError does not
    prevent HTTP jobs from being returned.
    """
    init_db()

    raw = RawJob(
        source="greenhouse",
        company="Stripe",
        title="Eng",
        url="https://x.com/li-exp-1",
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
            "moonlighter.discovery.scan.collection.discover_entry_points",
            return_value=[_FakeSessionExpiredSource],
        ),
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
        mock_browser.new_page = AsyncMock(return_value=make_mock_page())
        result = await scan_and_evaluate(context=make_test_context())

    assert "Stripe" in result  # HTTP job appears
    assert "_FakeSessionExpiredSource" in result  # warning appears too
