"""How the RemoteOK scanner maps the feed, survives failed responses and records its stats."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from moonlighter.discovery.sources.base import ScanStats, SourceStats
from moonlighter.discovery.sources.job_feeds.remoteok import RemoteOKScanner
from tests.discovery.sources.fake_http_clients import (
    make_mock_client,
    make_simple_client,
    mock_client_class,
)

_REMOTEOK_RESPONSE = [
    {"legal": "API Terms of Service: link back to Remote OK..."},
    {
        "id": "123",
        "company": "Acme",
        "position": "Senior Backend Engineer",
        "url": "https://remoteok.com/remote-jobs/123",
        "location": "Worldwide",
        "tags": ["python", "backend"],
        "description": "<p>Build <strong>things</strong>.</p>",
    },
    {
        "id": "124",
        "company": "",
        "position": "Frontend Dev",
        "url": "",  # missing url -> skipped
    },
]


async def test_remoteok_scan_maps_fields_and_skips_legal_notice_and_missing_url():
    mock_client = make_simple_client(_REMOTEOK_RESPONSE)
    with patch(
        "moonlighter.discovery.sources.job_feeds.remoteok.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemoteOKScanner().scan()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "remoteok"
    assert job.company == "Acme"
    assert job.title == "Senior Backend Engineer"
    assert job.url == "https://remoteok.com/remote-jobs/123"
    assert job.location == "Worldwide"
    assert job.remote_type == "remote"
    assert job.description == "Build things."


async def test_remoteok_missing_company_falls_back_to_source_name():
    response = [
        {
            "position": "Eng",
            "url": "https://remoteok.com/remote-jobs/1",
            "company": "",
        }
    ]
    mock_client = make_simple_client(response)
    with patch(
        "moonlighter.discovery.sources.job_feeds.remoteok.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemoteOKScanner().scan()
    assert jobs[0].company == "RemoteOK"


async def test_remoteok_network_exception_returns_empty():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "moonlighter.discovery.sources.job_feeds.remoteok.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemoteOKScanner().scan()
    assert jobs == []


async def test_remoteok_non_200_returns_empty():
    mock_client = make_simple_client({}, status=500)
    with patch(
        "moonlighter.discovery.sources.job_feeds.remoteok.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemoteOKScanner().scan()
    assert jobs == []


async def test_remoteok_non_list_json_returns_empty():
    mock_client = make_simple_client({"unexpected": "shape"})
    with patch(
        "moonlighter.discovery.sources.job_feeds.remoteok.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemoteOKScanner().scan()
    assert jobs == []


async def test_remoteok_non_json_body_returns_empty():
    """A 200 response with a non-JSON body (e.g. a Cloudflare interstitial --
    RemoteOK is Cloudflare-fronted) must degrade to [] like every other
    failure mode, not raise json.JSONDecodeError out of scan().
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "<html>", 0)
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "moonlighter.discovery.sources.job_feeds.remoteok.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemoteOKScanner().scan()
    assert jobs == []


async def test_remoteok_fetch_failure_logs_a_warning_with_the_traceback(caplog):
    mock_client = make_mock_client(raise_exception=httpx.ConnectError("boom"))
    with (
        patch(
            "moonlighter.discovery.sources.job_feeds.remoteok.httpx.AsyncClient",
            return_value=mock_client,
        ),
        caplog.at_level(logging.WARNING),
    ):
        await RemoteOKScanner().scan()
    remoteok_records = [
        record for record in caplog.records if record.getMessage().startswith("[remoteok]")
    ]
    assert [record.getMessage() for record in remoteok_records] == [
        "[remoteok] fetch failed: ConnectError: boom"
    ]
    assert remoteok_records[0].levelno == logging.WARNING
    assert remoteok_records[0].exc_info is not None


async def test_remoteok_tags_only_description_yields_none():
    response = [
        {"position": "Eng", "url": "https://remoteok.com/remote-jobs/1", "description": "<p></p>"}
    ]
    mock_client = make_simple_client(response)
    with patch(
        "moonlighter.discovery.sources.job_feeds.remoteok.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemoteOKScanner().scan()
    assert jobs[0].description is None


@pytest.mark.asyncio
async def test_remoteok_records_stats_on_failure():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(status_code=503))
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        stats: ScanStats = {}
        jobs = await RemoteOKScanner().scan(stats=stats)
    assert jobs == []
    assert stats["remoteok"] == SourceStats(companies=0, jobs=0, errors=1)


@pytest.mark.asyncio
async def test_remoteok_records_stats_on_success():
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = _REMOTEOK_RESPONSE
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok_response)
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        stats: ScanStats = {}
        jobs = await RemoteOKScanner().scan(stats=stats)
    assert stats["remoteok"].jobs == len(jobs) > 0
    assert stats["remoteok"].errors == 0
