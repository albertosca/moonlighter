"""An offer-shaped URL is read from its host's offers feed, matching the whole /o/{offer} segment and reading the remote flag as a value, and a failed, non-dict or unmatched feed returns None."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moonlighter.core.web.posting import fetch_posting_via_ats
from tests.core.web.posting.fake_client import fake_client

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


@pytest.mark.asyncio
async def test_recruitee_posting_carries_location_and_remote_flag():
    offers = {"offers": [{**RECRUITEE_OFFERS["offers"][0], "location": "Utrecht", "remote": True}]}
    client_class, _client_mock = fake_client(offers)
    with patch("httpx.AsyncClient", client_class):
        posting = await fetch_posting_via_ats("https://jobs.channable.com/o/backend-engineer")
    assert posting is not None
    assert posting.location == "Utrecht"
    assert posting.remote is True


@pytest.mark.asyncio
async def test_offer_shaped_url_routes_to_offers_api_on_same_host():
    client_class, client = fake_client(RECRUITEE_OFFERS)
    with patch("httpx.AsyncClient", client_class):
        posting = await fetch_posting_via_ats("https://jobs.channable.com/o/backend-engineer")
    assert posting is not None
    assert posting.company == "Channable"
    assert posting.title == "Backend Engineer"
    assert posting.description == "Elixir and Python."
    assert client.get.call_args.args[0] == "https://jobs.channable.com/api/offers/"


@pytest.mark.asyncio
async def test_offer_url_on_non_recruitee_host_falls_back_to_none():
    """A /o/{offer} path on a host that 404s the offers API is not Recruitee."""
    response = MagicMock(status_code=404)
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client_class = MagicMock()
    client_class.return_value.__aenter__ = AsyncMock(return_value=client)
    client_class.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", client_class):
        posting = await fetch_posting_via_ats("https://weird.site/o/thing")
    assert posting is None


@pytest.mark.asyncio
async def test_recruitee_non_dict_response_returns_none():
    client_class, _client_mock = fake_client(["unexpected", "shape"])
    with patch("httpx.AsyncClient", client_class):
        posting = await fetch_posting_via_ats("https://jobs.channable.com/o/backend-engineer")
    assert posting is None


@pytest.mark.asyncio
async def test_recruitee_offer_prefix_collision_does_not_match_longer_slug():
    """IMPORTANT regression: requesting /o/backend-engineer must not match a
    feed entry at /o/backend-engineer-senior — the old unanchored substring
    check (`needle in apply_url`) would wrongly return the senior posting.
    """
    collision = {
        "offers": [
            {
                "title": "Backend Engineer (Senior)",
                "company_name": "Channable",
                "description": "<p>Senior role.</p>",
                "careers_apply_url": "https://jobs.channable.com/o/backend-engineer-senior/c/new",
            },
            {
                "title": "Backend Engineer",
                "company_name": "Channable",
                "description": "<p>Elixir and Python.</p>",
                "careers_apply_url": "https://jobs.channable.com/o/backend-engineer/c/new",
            },
        ]
    }
    client_class, _client_mock = fake_client(collision)
    with patch("httpx.AsyncClient", client_class):
        posting = await fetch_posting_via_ats("https://jobs.channable.com/o/backend-engineer")
    assert posting is not None
    assert posting.title == "Backend Engineer"
    assert posting.company == "Channable"


@pytest.mark.asyncio
async def test_recruitee_longer_offer_slug_still_matches_itself():
    """Sanity twin of the collision test above: requesting the longer slug
    directly must still resolve to its own entry, not be blocked by the
    anchoring fix.
    """
    collision = {
        "offers": [
            {
                "title": "Backend Engineer",
                "company_name": "Channable",
                "description": "<p>Elixir and Python.</p>",
                "careers_apply_url": "https://jobs.channable.com/o/backend-engineer/c/new",
            },
            {
                "title": "Backend Engineer (Senior)",
                "company_name": "Channable",
                "description": "<p>Senior role.</p>",
                "careers_apply_url": "https://jobs.channable.com/o/backend-engineer-senior/c/new",
            },
        ]
    }
    client_class, _client_mock = fake_client(collision)
    with patch("httpx.AsyncClient", client_class):
        posting = await fetch_posting_via_ats(
            "https://jobs.channable.com/o/backend-engineer-senior"
        )
    assert posting is not None
    assert posting.title == "Backend Engineer (Senior)"


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
    client_class, _client_mock = fake_client(other_offer)
    with patch("httpx.AsyncClient", client_class):
        posting = await fetch_posting_via_ats("https://jobs.channable.com/o/backend-engineer")
    assert posting is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "remote"), [("false", False), ("true", True), (0, False), (None, False)]
)
async def test_recruitee_remote_flag_is_read_as_a_value_not_as_truthiness(flag, remote):
    """bool("false") is True: a string flag must not make an office job remote."""
    offers = {"offers": [{**RECRUITEE_OFFERS["offers"][0], "location": "Utrecht", "remote": flag}]}
    client_class, _client_mock = fake_client(offers)
    with patch("httpx.AsyncClient", client_class):
        posting = await fetch_posting_via_ats("https://jobs.channable.com/o/backend-engineer")
    assert posting is not None
    assert posting.remote is remote
