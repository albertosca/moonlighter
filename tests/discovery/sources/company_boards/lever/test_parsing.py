"""How a Lever posting becomes a job: fields, timestamps and the postings it skips."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moonlighter.discovery.sources.company_boards.lever import LeverScanner
from tests.discovery.sources.fake_http_clients import make_mock_client

LEVER_RESPONSE = [
    {
        "id": "abc-123",
        "text": "Staff Engineer",
        "hostedUrl": "https://jobs.lever.co/gitlab/abc-123",
        "categories": {"location": "Remote", "commitment": "Full-time"},
        "createdAt": 1716220800000,
        "descriptionPlain": "Build distributed systems in Elixir and Go.",
    }
]


@pytest.mark.asyncio
async def test_lever_scan():
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
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
    assert "Elixir" in jobs[0].description  # QUALITY-01: description extracted


async def test_lever_skips_entry_without_title():
    response = [
        {
            "id": "1",
            "text": "",
            "hostedUrl": "https://jobs.lever.co/co/1",
            "categories": {"location": "Remote"},
            "createdAt": 1716220800000,
        }
    ]
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.lever.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_skips_entry_without_url():
    response = [
        {
            "id": "1",
            "text": "Eng",
            "hostedUrl": "",
            "categories": {"location": "Remote"},
            "createdAt": 1716220800000,
        }
    ]
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.lever.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_timestamp_is_utc_aware():
    response = [
        {
            "id": "1",
            "text": "Eng",
            "hostedUrl": "https://jobs.lever.co/co/1",
            "categories": {"location": "Remote"},
            "createdAt": 1716220800000,
        }
    ]
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.lever.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await LeverScanner().scan(["co"])
    assert jobs[0].posted_at is not None
    assert jobs[0].posted_at.tzinfo is not None


async def test_lever_missing_created_at():
    response = [
        {
            "id": "1",
            "text": "Eng",
            "hostedUrl": "https://jobs.lever.co/co/1",
            "categories": {"location": "Remote"},
        }
    ]
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.lever.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await LeverScanner().scan(["co"])
    assert jobs[0].posted_at is None
