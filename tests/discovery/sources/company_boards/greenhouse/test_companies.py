"""How each Greenhouse company's fetch outcome reaches the scan: several boards, HTTP errors and wrong shapes."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from moonlighter.discovery.sources.company_boards.greenhouse import GreenhouseScanner
from tests.discovery.sources.fake_http_clients import make_mock_client


@pytest.mark.asyncio
async def test_greenhouse_404_skips_company():
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        scanner = GreenhouseScanner()
        jobs = await scanner.scan(["nonexistent-co"])

    assert jobs == []


async def test_greenhouse_network_exception_skips_company():
    mock_client = make_mock_client(raise_exception=httpx.ConnectError("timeout"))
    with patch(
        "moonlighter.discovery.sources.company_boards.greenhouse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_empty_jobs_list():
    mock_client = make_mock_client({"jobs": []})
    with patch(
        "moonlighter.discovery.sources.company_boards.greenhouse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_multiple_companies():
    response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": "2026-05-20T12:00:00Z",
            }
        ]
    }
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.greenhouse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await GreenhouseScanner().scan(["stripe", "linear"])
    assert len(jobs) == 2


async def test_greenhouse_partial_failure_continues():
    """1 of 3 companies returns 500; the other 2 succeed → jobs from 2 companies returned."""
    success_response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "absolute_url": "https://boards.greenhouse.io/ok/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": "2026-05-20T12:00:00Z",
            }
        ]
    }
    call_count = [0]

    async def get_with_partial_failure(url, **keyword_arguments):
        call_count[0] += 1
        http_response = MagicMock()
        if call_count[0] == 2:
            http_response.status_code = 500
        else:
            http_response.status_code = 200
            http_response.json.return_value = success_response
        return http_response

    mock_client = MagicMock()
    mock_client.get = get_with_partial_failure
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "moonlighter.discovery.sources.company_boards.greenhouse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await GreenhouseScanner().scan(["ok1", "fail", "ok2"])
    assert len(jobs) == 2


async def test_greenhouse_invalid_top_level_schema_returns_empty():
    """API retorna lista em vez de dict com 'jobs' → retorna [] sem crash."""
    mock_client = make_mock_client([{"title": "Eng"}])  # lista em vez de dict
    with patch(
        "moonlighter.discovery.sources.company_boards.greenhouse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_jobs_key_missing_returns_empty():
    """API retorna dict mas sem chave 'jobs' → retorna [] sem crash."""
    mock_client = make_mock_client({"data": []})  # sem 'jobs'
    with patch(
        "moonlighter.discovery.sources.company_boards.greenhouse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []
