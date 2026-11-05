"""How the Gupy scanner reports a failed search: empty results, the logged warning and the stats it records."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from moonlighter.discovery.sources.base import ScanStats, SourceStats
from moonlighter.discovery.sources.job_feeds.gupy import GupyScanner

from tests.discovery.sources.fake_http_clients import make_mock_client, mock_client_class
from tests.discovery.sources.job_feeds.gupy.fake_portal import GUPY_P1


async def test_gupy_500_response_returns_empty():
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs == []


async def test_gupy_non_json_body_returns_empty():
    """A 200 response with a non-JSON body (e.g. a Cloudflare/rate-limit
    interstitial page) must degrade to [] like every other failure mode,
    not raise json.JSONDecodeError out of scan() and abort the whole run."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "<html>", 0)
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs == []


async def test_gupy_non_dict_response_returns_empty():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"data": []}]
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs == []


async def test_gupy_network_exception_returns_empty():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs == []


async def test_gupy_fetch_failure_logs_a_warning_with_the_traceback(caplog):
    mock_client = make_mock_client(raise_exception=httpx.ConnectError("timeout"))
    with (
        patch(
            "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient",
            return_value=mock_client,
        ),
        caplog.at_level(logging.WARNING),
    ):
        await GupyScanner().scan(keywords="engenheiro")
    gupy_records = [record for record in caplog.records if record.getMessage().startswith("[gupy]")]
    assert [record.getMessage() for record in gupy_records] == [
        "[gupy] fetch failed: ConnectError: timeout"
    ]
    assert gupy_records[0].levelno == logging.WARNING
    assert gupy_records[0].exc_info is not None


@pytest.mark.asyncio
async def test_gupy_records_stats_on_failure():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(status_code=503))
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        stats: ScanStats = {}
        jobs = await GupyScanner().scan(keywords="eng", stats=stats)
    assert jobs == []
    assert stats["gupy"] == SourceStats(companies=0, jobs=0, errors=1)


@pytest.mark.asyncio
async def test_gupy_records_stats_on_success():
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = GUPY_P1
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok_response)
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        stats: ScanStats = {}
        jobs = await GupyScanner().scan(keywords="eng", stats=stats)
    assert stats["gupy"].jobs == len(jobs) > 0
    assert stats["gupy"].errors == 0
