import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from candidatador.scanner.http_sources import GreenhouseScanner, LeverScanner

GREENHOUSE_RESPONSE = {
    "jobs": [
        {
            "id": 123,
            "title": "Senior Software Engineer",
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/123",
            "location": {"name": "Remote"},
            "updated_at": "2026-05-20T12:00:00Z",
        }
    ]
}

LEVER_RESPONSE = [
    {
        "id": "abc-123",
        "text": "Staff Engineer",
        "hostedUrl": "https://jobs.lever.co/gitlab/abc-123",
        "categories": {"location": "Remote", "commitment": "Full-time"},
        "createdAt": 1716220800000,
    }
]

@pytest.mark.asyncio
async def test_greenhouse_scan():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = GREENHOUSE_RESPONSE
        mock_client.get = AsyncMock(return_value=mock_response)

        scanner = GreenhouseScanner()
        jobs = await scanner.scan(["stripe"])

    assert len(jobs) == 1
    assert jobs[0].company == "stripe"
    assert jobs[0].title == "Senior Software Engineer"
    assert jobs[0].remote_type == "remote"
    assert jobs[0].source == "greenhouse"

@pytest.mark.asyncio
async def test_lever_scan():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = LEVER_RESPONSE
        mock_client.get = AsyncMock(return_value=mock_response)

        scanner = LeverScanner()
        jobs = await scanner.scan(["gitlab"])

    assert len(jobs) == 1
    assert jobs[0].company == "gitlab"
    assert jobs[0].title == "Staff Engineer"
    assert jobs[0].remote_type == "remote"
    assert jobs[0].source == "lever"

@pytest.mark.asyncio
async def test_greenhouse_404_skips_company():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        scanner = GreenhouseScanner()
        jobs = await scanner.scan(["nonexistent-co"])

    assert jobs == []
