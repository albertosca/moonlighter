"""How each Ashby company's fetch outcome reaches the scan: HTTP errors and every wrong shape of the jobs list."""

from unittest.mock import patch

import httpx

from moonlighter.discovery.sources.company_boards.ashby import AshbyScanner
from tests.discovery.sources.company_boards.ashby.fake_board import ashby_response
from tests.discovery.sources.fake_http_clients import make_mock_client


async def test_ashby_500_response_skips_company():
    mock_client = make_mock_client({}, status_code=500)
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_network_exception_skips_company():
    mock_client = make_mock_client(raise_exception=httpx.ConnectError("timeout"))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_empty_jobs_returns_empty():
    mock_client = make_mock_client(ashby_response())
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_jobs_not_a_list_returns_empty():
    mock_client = make_mock_client({"jobs": {"unexpected": "shape"}})
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_null_jobs_returns_empty():
    mock_client = make_mock_client({"jobs": None})
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_non_dict_response_returns_empty():
    mock_client = make_mock_client([{"title": "Eng"}])
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []
