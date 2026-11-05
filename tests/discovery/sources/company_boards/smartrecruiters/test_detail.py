"""How the SmartRecruiters scanner builds a description from a posting's detail, or degrades without one."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from moonlighter.discovery.sources.company_boards.smartrecruiters import SmartRecruitersScanner

from tests.discovery.sources.company_boards.smartrecruiters.fake_board import (
    SR_LIST_P1,
    make_url_branching_client,
    sr_response,
)

# SR_LIST_P1 reports totalFound=2 with only 1 item on this page, so _list keeps
# paginating; the detail-failure tests below only care about page 1, so they close
# pagination with this empty second page rather than hand-waving it away like the
# old blanket try/except did.
_SR_LIST_EMPTY_P2 = {"offset": 1, "limit": 1, "totalFound": 2, "content": []}


async def test_smartrecruiters_detail_500_yields_none_description():
    mock_client = make_url_branching_client({"postings?limit=100&offset=0": SR_LIST_P1})

    async def fake_get(url, headers=None):
        if "postings?limit=100&offset=0" in url:
            return sr_response(SR_LIST_P1)
        if "postings?limit=100&offset=1" in url:
            return sr_response(_SR_LIST_EMPTY_P2)
        if "postings/744000000000001" in url:
            return sr_response({}, status_code=500)
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client.get = AsyncMock(side_effect=fake_get)
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
    assert len(jobs) == 1
    assert jobs[0].description is None


async def test_smartrecruiters_detail_network_exception_yields_none_description():
    async def fake_get(url, headers=None):
        if "postings?limit=100&offset=0" in url:
            return sr_response(SR_LIST_P1)
        if "postings?limit=100&offset=1" in url:
            return sr_response(_SR_LIST_EMPTY_P2)
        if "postings/744000000000001" in url:
            raise httpx.ConnectError("timeout")
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
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
    assert len(jobs) == 1
    assert jobs[0].description is None


async def test_smartrecruiters_detail_non_dict_response_yields_none_description():
    async def fake_get(url, headers=None):
        if "postings?limit=100&offset=0" in url:
            return sr_response(SR_LIST_P1)
        if "postings?limit=100&offset=1" in url:
            return sr_response(_SR_LIST_EMPTY_P2)
        if "postings/744000000000001" in url:
            return sr_response([{"jobAd": {}}])
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
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
    assert len(jobs) == 1
    assert jobs[0].description is None


async def test_smartrecruiters_detail_multiple_sections_concatenated_and_html_stripped():
    detail = {
        "jobAd": {
            "sections": {
                "jobDescription": {"text": "<p>Own the pipeline.</p>"},
                "qualifications": {"text": "<ul><li>5+ years</li></ul>"},
                "notASection": "ignored, not a dict",
            }
        }
    }
    page = {
        "offset": 0,
        "limit": 100,
        "totalFound": 1,
        "content": [{"id": "744000000000012", "name": "Eng", "location": {}}],
    }
    mock_client = make_url_branching_client(
        {
            "postings?limit=100&offset=0": page,
            "postings/744000000000012": detail,
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
    description = jobs[0].description
    assert description is not None
    assert "<" not in description
    assert ">" not in description
    assert "Own the pipeline." in description
    assert "5+ years" in description


async def test_smartrecruiters_detail_no_sections_yields_none_description():
    detail = {"jobAd": {"sections": {}}}
    page = {
        "offset": 0,
        "limit": 100,
        "totalFound": 1,
        "content": [{"id": "744000000000013", "name": "Eng", "location": {}}],
    }
    mock_client = make_url_branching_client(
        {
            "postings?limit=100&offset=0": page,
            "postings/744000000000013": detail,
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
    assert jobs[0].description is None
