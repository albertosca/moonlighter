"""How the SmartRecruiters scanner reads the postings list: failed responses, skipped postings and locations."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from moonlighter.discovery.sources.company_boards.smartrecruiters import SmartRecruitersScanner

from tests.discovery.sources.company_boards.smartrecruiters.fake_board import (
    SR_DETAIL,
    make_url_branching_client,
    sr_response,
)


def _make_flat_client(response=None, status_code=200, raise_exception=None):
    """Like make_mock_client but scoped locally to keep SmartRecruiters tests grouped."""
    mock_client = MagicMock()
    if raise_exception:
        mock_client.get = AsyncMock(side_effect=raise_exception)
    else:
        mock_client.get = AsyncMock(return_value=sr_response(response, status_code=status_code))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_smartrecruiters_500_response_returns_empty():
    mock_client = _make_flat_client({}, status_code=500)
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.httpx.AsyncClient",
            return_value=mock_client,
        ),
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.asyncio.sleep",
            AsyncMock(),
        ),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []


async def test_smartrecruiters_non_dict_list_response_returns_empty():
    mock_client = _make_flat_client([{"content": []}])
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.httpx.AsyncClient",
            return_value=mock_client,
        ),
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.asyncio.sleep",
            AsyncMock(),
        ),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []


async def test_smartrecruiters_network_exception_on_list_skips_company():
    mock_client = _make_flat_client(raise_exception=httpx.ConnectError("timeout"))
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.httpx.AsyncClient",
            return_value=mock_client,
        ),
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.asyncio.sleep",
            AsyncMock(),
        ),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []


async def test_smartrecruiters_skips_posting_without_id_or_name():
    page = {
        "offset": 0,
        "limit": 100,
        "totalFound": 2,
        "content": [
            {"id": "", "name": "No ID", "location": {}},
            {"id": "744000000000009", "name": "", "location": {}},
        ],
    }
    mock_client = make_url_branching_client({"postings?limit=100&offset=0": page})
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.httpx.AsyncClient",
            return_value=mock_client,
        ),
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.asyncio.sleep",
            AsyncMock(),
        ),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []


async def test_smartrecruiters_no_remote_or_hybrid_flags_uses_location_text():
    page = {
        "offset": 0,
        "limit": 100,
        "totalFound": 1,
        "content": [
            {
                "id": "744000000000010",
                "name": "Support",
                "location": {"city": "Berlin", "country": "Germany"},
            }
        ],
    }
    mock_client = make_url_branching_client(
        {
            "postings?limit=100&offset=0": page,
            "postings/744000000000010": SR_DETAIL,
        }
    )
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.httpx.AsyncClient",
            return_value=mock_client,
        ),
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.asyncio.sleep",
            AsyncMock(),
        ),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs[0].location == "Berlin, Germany"
    assert jobs[0].remote_type is None  # bare city: unknown, never invented onsite


async def test_smartrecruiters_missing_location_dict():
    page = {
        "offset": 0,
        "limit": 100,
        "totalFound": 1,
        "content": [{"id": "744000000000011", "name": "No Location"}],
    }
    mock_client = make_url_branching_client(
        {
            "postings?limit=100&offset=0": page,
            "postings/744000000000011": SR_DETAIL,
        }
    )
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.httpx.AsyncClient",
            return_value=mock_client,
        ),
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.asyncio.sleep",
            AsyncMock(),
        ),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs[0].location is None
    assert jobs[0].remote_type is None
