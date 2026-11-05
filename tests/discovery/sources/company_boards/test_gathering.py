"""The shared parallel fetch behind every company board: logging, failed slugs and per-source stats."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moonlighter.discovery.sources.base import ScanStats, SourceStats
from moonlighter.discovery.sources.company_boards.ashby import AshbyScanner
from moonlighter.discovery.sources.company_boards.greenhouse import GreenhouseScanner
from moonlighter.discovery.sources.company_boards.lever import LeverScanner
from moonlighter.discovery.sources.company_boards.recruitee import RecruiteeScanner
from moonlighter.discovery.sources.company_boards.workable import WorkableScanner
from tests.discovery.sources.company_boards.greenhouse_board import GREENHOUSE_RESPONSE
from tests.discovery.sources.fake_http_clients import make_mock_client, mock_client_class


@pytest.mark.asyncio
async def test_greenhouse_logs_scan_start_and_fetched(caplog):
    scanner = GreenhouseScanner()
    payload = {
        "jobs": [
            {
                "title": "SWE",
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": None,
                "content": "",
            }
        ]
    }
    mock_client = make_mock_client(payload)
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.gathering.httpx.AsyncClient",
            return_value=mock_client,
        ),
        caplog.at_level(
            logging.INFO, logger="moonlighter.discovery.sources.company_boards.gathering"
        ),
    ):
        await scanner.scan(["co"])
    assert "greenhouse" in caplog.text
    assert "scanning" in caplog.text
    assert "fetched" in caplog.text


@pytest.mark.asyncio
async def test_lever_logs_scan_fetched(caplog):
    scanner = LeverScanner()
    payload = [
        {
            "text": "Eng",
            "hostedUrl": "https://jobs.lever.co/co/1",
            "categories": {"location": "Remote"},
            "createdAt": 0,
        }
    ]
    mock_client = make_mock_client(payload)
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.gathering.httpx.AsyncClient",
            return_value=mock_client,
        ),
        caplog.at_level(
            logging.INFO, logger="moonlighter.discovery.sources.company_boards.gathering"
        ),
    ):
        await scanner.scan(["co"])
    assert "lever" in caplog.text
    assert "fetched" in caplog.text


@pytest.mark.parametrize(
    "scanner_class",
    [GreenhouseScanner, LeverScanner, AshbyScanner, WorkableScanner, RecruiteeScanner],
)
async def test_scan_skips_fetch_exceptions(scanner_class):
    """_fetch raises → gather(return_exceptions) returns the exception → ignored (not a list)."""
    mock_client = make_mock_client({})
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.gathering.httpx.AsyncClient",
            return_value=mock_client,
        ),
        patch.object(scanner_class, "_fetch", new=AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        jobs = await scanner_class().scan(["co"])
    assert jobs == []


@pytest.mark.asyncio
async def test_gather_jobs_counts_failures_per_source():
    """One slug succeeds, one errors: the error is COUNTED in stats, not silently
    dropped — [] from a broken API must stay distinguishable from no openings.
    """
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = GREENHOUSE_RESPONSE
    boom = MagicMock(status_code=500)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[ok_response, boom])
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        stats: ScanStats = {}
        jobs = await GreenhouseScanner().scan(["stripe", "deadco"], stats=stats)
    assert len(jobs) == 1
    assert stats["greenhouse"] == SourceStats(companies=2, jobs=1, errors=1)


@pytest.mark.asyncio
async def test_scan_without_stats_still_works():
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = GREENHOUSE_RESPONSE
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok_response)
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        jobs = await GreenhouseScanner().scan(["stripe"])
    assert len(jobs) == 1
