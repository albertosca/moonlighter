"""How the SmartRecruiters scanner pages through a company's postings and always stops."""

from unittest.mock import AsyncMock, patch

from moonlighter.discovery.sources.company_boards.smartrecruiters import SmartRecruitersScanner
from tests.discovery.sources.company_boards.smartrecruiters.fake_board import (
    SR_DETAIL,
    SR_LIST_P1,
    make_url_branching_client,
)

_SR_LIST_P2 = {
    "offset": 1,
    "limit": 1,
    "totalFound": 2,
    "content": [
        {
            "id": "744000000000002",
            "uuid": "u2",
            "name": "Data Eng",
            "location": {"city": "NYC", "country": "US", "remote": False, "hybrid": True},
        }
    ],
}


async def test_smartrecruiters_paginates_and_fetches_detail():
    mock_client = make_url_branching_client(
        {
            "postings?limit=100&offset=0": SR_LIST_P1,
            "postings?limit=100&offset=1": _SR_LIST_P2,
            "postings/744000000000001": SR_DETAIL,
            "postings/744000000000002": SR_DETAIL,
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
        jobs = await SmartRecruitersScanner().scan(["Visa"])

    assert len(jobs) == 2
    first, second = jobs
    assert first.source == "smartrecruiters"
    assert first.company == "Visa"
    assert first.title == "SRE"
    assert first.url == "https://jobs.smartrecruiters.com/Visa/744000000000001"
    assert first.remote_type == "remote"
    assert first.description == "Own the pipeline"

    assert second.title == "Data Eng"
    assert second.url == "https://jobs.smartrecruiters.com/Visa/744000000000002"
    assert second.remote_type == "hybrid"
    assert second.description == "Own the pipeline"


async def test_smartrecruiters_empty_feed_makes_no_detail_call():
    empty_page = {"offset": 0, "limit": 100, "totalFound": 0, "content": []}
    mock_client = make_url_branching_client({"postings?limit=100&offset=0": empty_page})
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.httpx.AsyncClient",
            return_value=mock_client,
        ),
        patch(
            "moonlighter.discovery.sources.company_boards.smartrecruiters.asyncio.sleep",
            AsyncMock(),
        ) as mock_sleep,
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []
    mock_sleep.assert_not_called()
    # only the single list call was made, no detail call (asserted implicitly by
    # make_url_branching_client raising on any unmapped URL, e.g. a detail URL)
    assert mock_client.get.await_count == 1


async def test_smartrecruiters_pagination_terminates_when_content_shorter_than_limit():
    # totalFound overstates what's actually returned; the loop must still terminate
    # because `content` comes back empty on the second page, not because offset caught up.
    page = {"offset": 0, "limit": 100, "totalFound": 5, "content": []}
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
    assert mock_client.get.await_count == 1


async def test_smartrecruiters_pagination_terminates_when_offset_reaches_total():
    mock_client = make_url_branching_client(
        {
            "postings?limit=100&offset=0": SR_LIST_P1,
            "postings?limit=100&offset=1": _SR_LIST_P2,
            "postings/744000000000001": SR_DETAIL,
            "postings/744000000000002": SR_DETAIL,
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
        await SmartRecruitersScanner().scan(["Visa"])
    # exactly 2 list calls (offset=0, offset=1) then it stops -- proves offset>=total
    # terminates the loop rather than spinning past totalFound.
    list_calls = [
        await_call
        for await_call in mock_client.get.await_args_list
        if "postings?limit=100" in await_call.args[0]
    ]
    assert len(list_calls) == 2


async def test_smartrecruiters_zero_limit_field_does_not_spin():
    # The server explicitly reports "limit": 0 while still returning content and a
    # totalFound far larger than what's been consumed so far. If the loop advanced
    # offset by data.get("limit", 100) it would add 0 and re-request the SAME offset
    # forever (bounded here only by make_url_branching_client raising on an
    # unexpected URL, which would surface as a failure rather than a real hang).
    # Advancing by len(content) instead guarantees the offset moves forward every
    # iteration, so the loop terminates as soon as a page comes back empty.
    spinning_page = {
        "offset": 0,
        "limit": 0,
        "totalFound": 999999,
        "content": [{"id": "1", "uuid": "u1", "name": "Spinner"}],
    }
    empty_page = {"offset": 1, "limit": 0, "totalFound": 999999, "content": []}
    mock_client = make_url_branching_client(
        {
            "postings?limit=100&offset=0": spinning_page,
            "postings?limit=100&offset=1": empty_page,
            "postings/1": SR_DETAIL,
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

    assert len(jobs) == 1
    list_calls = [
        await_call
        for await_call in mock_client.get.await_args_list
        if "postings?limit=100" in await_call.args[0]
    ]
    assert len(list_calls) == 2
