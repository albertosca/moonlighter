from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.discovery.posting import FetchedPosting, fetch_posting_via_ats

GREENHOUSE_JOB = {
    "title": "Account Executive",
    "company_name": "GitLab",
    # Live-verified 2026-08-12: the board API returns content HTML-entity-escaped.
    "content": "&lt;div&gt;&lt;p&gt;Build things.&lt;/p&gt;&lt;/div&gt;",
}

RECRUITEE_OFFERS = {
    "offers": [
        {
            "title": "Backend Engineer",
            "company_name": "Channable",
            "description": "<p>Elixir and Python.</p>",
            "careers_apply_url": "https://jobs.channable.com/o/backend-engineer/c/new",
        }
    ]
}


def _client(response_json):
    response = MagicMock(status_code=200)
    response.json.return_value = response_json
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    cls = MagicMock()
    cls.return_value.__aenter__ = AsyncMock(return_value=client)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return cls, client


@pytest.mark.asyncio
async def test_greenhouse_url_routes_to_board_api():
    cls, client = _client(GREENHOUSE_JOB)
    with patch("httpx.AsyncClient", cls):
        posting = await fetch_posting_via_ats("https://boards.greenhouse.io/gitlab/jobs/8503792002")
    assert posting == FetchedPosting(
        company="GitLab", title="Account Executive", description="Build things."
    )
    assert (
        client.get.call_args.args[0]
        == "https://boards-api.greenhouse.io/v1/boards/gitlab/jobs/8503792002"
    )


@pytest.mark.asyncio
async def test_offer_shaped_url_routes_to_offers_api_on_same_host():
    cls, client = _client(RECRUITEE_OFFERS)
    with patch("httpx.AsyncClient", cls):
        posting = await fetch_posting_via_ats("https://jobs.channable.com/o/backend-engineer")
    assert posting is not None
    assert posting.company == "Channable"
    assert posting.title == "Backend Engineer"
    assert posting.description == "Elixir and Python."
    assert client.get.call_args.args[0] == "https://jobs.channable.com/api/offers/"


@pytest.mark.asyncio
async def test_unrecognized_url_returns_none():
    posting = await fetch_posting_via_ats("https://example.com/careers/dev")
    assert posting is None


@pytest.mark.asyncio
async def test_offer_url_on_non_recruitee_host_falls_back_to_none():
    """A /o/{offer} path on a host that 404s the offers API is not Recruitee."""
    response = MagicMock(status_code=404)
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    cls = MagicMock()
    cls.return_value.__aenter__ = AsyncMock(return_value=client)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", cls):
        posting = await fetch_posting_via_ats("https://weird.site/o/thing")
    assert posting is None


@pytest.mark.asyncio
async def test_greenhouse_fetch_error_returns_none():
    """A non-200 from the board API (e.g. a stale/deleted job_id) is a FetchError,
    swallowed so the caller falls back to the generic HTML fetch."""
    response = MagicMock(status_code=404)
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    cls = MagicMock()
    cls.return_value.__aenter__ = AsyncMock(return_value=client)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", cls):
        posting = await fetch_posting_via_ats("https://boards.greenhouse.io/gitlab/jobs/8503792002")
    assert posting is None


@pytest.mark.asyncio
async def test_greenhouse_non_dict_response_returns_none():
    cls, _client_mock = _client(["unexpected", "shape"])
    with patch("httpx.AsyncClient", cls):
        posting = await fetch_posting_via_ats("https://boards.greenhouse.io/gitlab/jobs/8503792002")
    assert posting is None


@pytest.mark.asyncio
async def test_recruitee_non_dict_response_returns_none():
    cls, _client_mock = _client(["unexpected", "shape"])
    with patch("httpx.AsyncClient", cls):
        posting = await fetch_posting_via_ats("https://jobs.channable.com/o/backend-engineer")
    assert posting is None


@pytest.mark.asyncio
async def test_recruitee_offer_not_in_list_returns_none():
    """The offers feed has entries, but none match the requested /o/{offer} slug."""
    other_offer = {
        "offers": [
            {
                "title": "Frontend Engineer",
                "company_name": "Channable",
                "description": "<p>React.</p>",
                "careers_apply_url": "https://jobs.channable.com/o/frontend-engineer/c/new",
            }
        ]
    }
    cls, _client_mock = _client(other_offer)
    with patch("httpx.AsyncClient", cls):
        posting = await fetch_posting_via_ats("https://jobs.channable.com/o/backend-engineer")
    assert posting is None
