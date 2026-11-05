"""How the Remotive scanner maps the feed, survives failed responses and records its stats."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from moonlighter.discovery.sources.base import ScanStats, SourceStats
from moonlighter.discovery.sources.job_feeds.remotive import RemotiveScanner

from tests.discovery.sources.fake_http_clients import (
    make_mock_client,
    make_simple_client,
    mock_client_class,
)

_REMOTIVE_RESPONSE = {
    "jobs": [
        {
            "id": 1,
            "title": "Senior Python Engineer",
            "company_name": "Acme",
            "url": "https://remotive.com/remote-jobs/1",
            "candidate_required_location": "Worldwide",
            "description": "<p>Build <strong>things</strong>.</p>",
        },
        {
            "id": 2,
            "title": "",  # missing title -> skipped
            "company_name": "Beta",
            "url": "https://remotive.com/remote-jobs/2",
        },
    ]
}


async def test_remotive_scan_maps_fields_and_skips_missing_title():
    mock_client = make_simple_client(_REMOTIVE_RESPONSE)
    with patch(
        "moonlighter.discovery.sources.job_feeds.remotive.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemotiveScanner().scan()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "remotive"
    assert job.company == "Acme"
    assert job.title == "Senior Python Engineer"
    assert job.url == "https://remotive.com/remote-jobs/1"
    assert job.location == "Worldwide"
    assert job.remote_type == "remote"
    assert job.description == "Build things."


async def test_remotive_missing_company_falls_back_to_source_name():
    response = {"jobs": [{"title": "Eng", "url": "https://remotive.com/1", "company_name": ""}]}
    mock_client = make_simple_client(response)
    with patch(
        "moonlighter.discovery.sources.job_feeds.remotive.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemotiveScanner().scan()
    assert jobs[0].company == "Remotive"


async def test_remotive_no_jobs_key_returns_empty():
    mock_client = make_simple_client({"job-count": 0})
    with patch(
        "moonlighter.discovery.sources.job_feeds.remotive.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemotiveScanner().scan()
    assert jobs == []


async def test_remotive_network_exception_returns_empty():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "moonlighter.discovery.sources.job_feeds.remotive.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemotiveScanner().scan()
    assert jobs == []


async def test_remotive_non_dict_json_returns_empty():
    mock_client = make_simple_client(["unexpected", "shape"])
    with patch(
        "moonlighter.discovery.sources.job_feeds.remotive.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemotiveScanner().scan()
    assert jobs == []


async def test_remotive_non_json_body_returns_empty():
    """A 200 response with a non-JSON body must degrade to [] like every
    other failure mode, not raise json.JSONDecodeError out of scan()."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "<html>", 0)
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "moonlighter.discovery.sources.job_feeds.remotive.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemotiveScanner().scan()
    assert jobs == []


async def test_remotive_non_200_returns_empty():
    mock_client = make_simple_client({}, status=500)
    with patch(
        "moonlighter.discovery.sources.job_feeds.remotive.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemotiveScanner().scan()
    assert jobs == []


async def test_remotive_fetch_failure_logs_a_warning_with_the_traceback(caplog):
    mock_client = make_mock_client(raise_exception=httpx.ConnectError("boom"))
    with (
        patch(
            "moonlighter.discovery.sources.job_feeds.remotive.httpx.AsyncClient",
            return_value=mock_client,
        ),
        caplog.at_level(logging.WARNING),
    ):
        await RemotiveScanner().scan()
    remotive_records = [
        record for record in caplog.records if record.getMessage().startswith("[remotive]")
    ]
    assert [record.getMessage() for record in remotive_records] == [
        "[remotive] fetch failed: ConnectError: boom"
    ]
    assert remotive_records[0].levelno == logging.WARNING
    assert remotive_records[0].exc_info is not None


async def test_remotive_tags_only_description_yields_none():
    response = {
        "jobs": [{"title": "Eng", "url": "https://remotive.com/1", "description": "<p></p>"}]
    }
    mock_client = make_simple_client(response)
    with patch(
        "moonlighter.discovery.sources.job_feeds.remotive.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RemotiveScanner().scan()
    assert jobs[0].description is None


@pytest.mark.asyncio
async def test_remotive_records_stats_on_failure():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(status_code=503))
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        stats: ScanStats = {}
        jobs = await RemotiveScanner().scan(stats=stats)
    assert jobs == []
    assert stats["remotive"] == SourceStats(companies=0, jobs=0, errors=1)


@pytest.mark.asyncio
async def test_remotive_records_stats_on_success():
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = _REMOTIVE_RESPONSE
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok_response)
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        stats: ScanStats = {}
        jobs = await RemotiveScanner().scan(stats=stats)
    assert stats["remotive"].jobs == len(jobs) > 0
    assert stats["remotive"].errors == 0
