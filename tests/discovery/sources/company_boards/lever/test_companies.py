"""How each Lever company's fetch outcome reaches the scan: several boards, HTTP errors and wrong shapes."""

from unittest.mock import patch

import httpx

from moonlighter.discovery.sources.company_boards.lever import LeverScanner
from tests.discovery.sources.fake_http_clients import make_mock_client


async def test_lever_network_exception_skips_company():
    mock_client = make_mock_client(raise_exception=httpx.ConnectError("timeout"))
    with patch(
        "moonlighter.discovery.sources.company_boards.lever.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_500_response_skips_company():
    mock_client = make_mock_client([], status_code=500)
    with patch(
        "moonlighter.discovery.sources.company_boards.lever.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_empty_array_response():
    mock_client = make_mock_client([])
    with patch(
        "moonlighter.discovery.sources.company_boards.lever.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_multiple_companies_returns_all():
    """2 Lever companies each with 1 job → 2 jobs total."""
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
        jobs = await LeverScanner().scan(["stripe", "linear"])
    assert len(jobs) == 2
    assert jobs[0].company == "stripe"
    assert jobs[1].company == "linear"


async def test_lever_non_list_response_returns_empty():
    """API retorna dict (ex: erro) em vez de lista → retorna [] sem crash."""
    mock_client = make_mock_client({"error": "rate limited"})
    with patch(
        "moonlighter.discovery.sources.company_boards.lever.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []
