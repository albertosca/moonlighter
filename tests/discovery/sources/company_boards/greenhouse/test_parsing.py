"""How a Greenhouse posting becomes a job: fields, HTML, dates and the postings it skips."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moonlighter.discovery.sources.company_boards.greenhouse import GreenhouseScanner
from tests.discovery.sources.company_boards.greenhouse_board import GREENHOUSE_RESPONSE
from tests.discovery.sources.fake_http_clients import make_mock_client


@pytest.mark.asyncio
async def test_greenhouse_scan():
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
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


async def test_greenhouse_html_stripped_from_description():
    response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": "2026-05-20T12:00:00Z",
                "content": "<p>Hello</p><br/>World",
            }
        ]
    }
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.greenhouse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await GreenhouseScanner().scan(["co"])
    assert len(jobs) == 1
    assert "<" not in jobs[0].description
    assert ">" not in jobs[0].description
    assert "Hello" in jobs[0].description


async def test_greenhouse_posted_at_parsed():
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
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs[0].posted_at is not None
    assert isinstance(jobs[0].posted_at, datetime)


async def test_greenhouse_date_only_updated_at_with_z_suffix_parses_to_naive_midnight():
    response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": "2024-01-01Z",
            }
        ]
    }
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.greenhouse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs[0].posted_at is not None
    assert jobs[0].posted_at.isoformat() == "2024-01-01T00:00:00"


async def test_greenhouse_posted_at_invalid_format():
    response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": "not-a-date",
            }
        ]
    }
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.greenhouse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs[0].posted_at is None


async def test_greenhouse_missing_location():
    response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "updated_at": "2026-05-20T12:00:00Z",
            }
        ]
    }
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.greenhouse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs[0].location is None
    assert jobs[0].remote_type is None


async def test_greenhouse_missing_title_skips_job():
    """Item with no 'title' is skipped — does not raise KeyError."""
    response = {
        "jobs": [
            {
                "id": 1,
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": "2026-05-20T12:00:00Z",
            },
        ]
    }
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.greenhouse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_missing_absolute_url_skips_job():
    """Item with no 'absolute_url' is skipped."""
    response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "location": {"name": "Remote"},
                "updated_at": "2026-05-20T12:00:00Z",
            },
        ]
    }
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.greenhouse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []
