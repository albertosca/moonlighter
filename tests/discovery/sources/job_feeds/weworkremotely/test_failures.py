"""How the We Work Remotely scanner reports a failed or malformed feed: empty results, warnings and stats."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from moonlighter.discovery.sources.base import ScanStats, SourceStats
from moonlighter.discovery.sources.job_feeds.weworkremotely import WeWorkRemotelyScanner

from tests.discovery.sources.fake_http_clients import make_mock_client, mock_client_class
from tests.discovery.sources.job_feeds.weworkremotely.fake_feed import WWR_RSS, make_rss_client


async def test_wwr_network_exception_returns_empty():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WeWorkRemotelyScanner().scan()
    assert jobs == []


async def test_wwr_non_200_returns_empty():
    mock_client = make_rss_client("", status=500)
    with patch(
        "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WeWorkRemotelyScanner().scan()
    assert jobs == []


async def test_wwr_malformed_xml_returns_empty():
    mock_client = make_rss_client("<not-valid-xml")
    with patch(
        "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WeWorkRemotelyScanner().scan()
    assert jobs == []


async def test_wwr_fetch_failure_logs_a_warning_with_the_traceback(caplog):
    mock_client = make_mock_client(raise_exception=httpx.ConnectError("boom"))
    with (
        patch(
            "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
            return_value=mock_client,
        ),
        caplog.at_level(logging.WARNING),
    ):
        await WeWorkRemotelyScanner().scan()
    feed_records = [
        record for record in caplog.records if record.getMessage().startswith("[weworkremotely]")
    ]
    assert [record.getMessage() for record in feed_records] == [
        "[weworkremotely] fetch failed: boom"
    ]
    assert feed_records[0].levelno == logging.WARNING
    assert feed_records[0].exc_info is not None


async def test_wwr_http_error_status_logs_a_warning(caplog):
    mock_client = make_rss_client("", status=500)
    with (
        patch(
            "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
            return_value=mock_client,
        ),
        caplog.at_level(logging.WARNING),
    ):
        await WeWorkRemotelyScanner().scan()
    feed_records = [
        record for record in caplog.records if record.getMessage().startswith("[weworkremotely]")
    ]
    assert [record.getMessage() for record in feed_records] == [
        "[weworkremotely] fetch failed: HTTP 500"
    ]
    assert feed_records[0].levelno == logging.WARNING
    assert feed_records[0].exc_info is None


async def test_wwr_malformed_feed_logs_a_warning_with_the_traceback(caplog):
    mock_client = make_rss_client("<not-valid-xml")
    with (
        patch(
            "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
            return_value=mock_client,
        ),
        caplog.at_level(logging.WARNING),
    ):
        await WeWorkRemotelyScanner().scan()
    feed_records = [
        record for record in caplog.records if record.getMessage().startswith("[weworkremotely]")
    ]
    assert [record.getMessage() for record in feed_records] == [
        "[weworkremotely] malformed feed: unclosed token: line 1, column 0"
    ]
    assert feed_records[0].levelno == logging.WARNING
    assert feed_records[0].exc_info is not None


@pytest.mark.asyncio
async def test_wwr_records_stats_on_failure():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(status_code=503))
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        stats: ScanStats = {}
        jobs = await WeWorkRemotelyScanner().scan(stats=stats)
    assert jobs == []
    assert stats["weworkremotely"] == SourceStats(companies=0, jobs=0, errors=1)


@pytest.mark.asyncio
async def test_wwr_records_stats_on_success():
    ok_response = MagicMock(status_code=200)
    ok_response.text = WWR_RSS
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok_response)
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        stats: ScanStats = {}
        jobs = await WeWorkRemotelyScanner().scan(stats=stats)
    assert stats["weworkremotely"].jobs == len(jobs) > 0
    assert stats["weworkremotely"].errors == 0
