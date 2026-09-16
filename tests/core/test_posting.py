from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.core.posting import (
    FetchedPosting,
    fetch_description,
    fetch_posting_via_ats,
    strip_tags,
)

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
async def test_recruitee_offer_prefix_collision_does_not_match_longer_slug():
    """IMPORTANT regression: requesting /o/backend-engineer must not match a
    feed entry at /o/backend-engineer-senior — the old unanchored substring
    check (`needle in apply_url`) would wrongly return the senior posting."""
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
    cls, _client_mock = _client(collision)
    with patch("httpx.AsyncClient", cls):
        posting = await fetch_posting_via_ats("https://jobs.channable.com/o/backend-engineer")
    assert posting is not None
    assert posting.title == "Backend Engineer"
    assert posting.company == "Channable"


@pytest.mark.asyncio
async def test_recruitee_longer_offer_slug_still_matches_itself():
    """Sanity twin of the collision test above: requesting the longer slug
    directly must still resolve to its own entry, not be blocked by the
    anchoring fix."""
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
    cls, _client_mock = _client(collision)
    with patch("httpx.AsyncClient", cls):
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
    cls, _client_mock = _client(other_offer)
    with patch("httpx.AsyncClient", cls):
        posting = await fetch_posting_via_ats("https://jobs.channable.com/o/backend-engineer")
    assert posting is None


async def test_fetch_description_drops_style_and_script_contents():
    html_page = "<style>.a{color:red}</style><script>var x=1;</script><p>Real text</p>"
    response = MagicMock(status_code=200, text=html_page)
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    cls = MagicMock()
    cls.return_value.__aenter__ = AsyncMock(return_value=client)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", cls):
        description, error = await fetch_description("https://example.com/job")
    assert error is None
    assert description == "Real text"
    assert "color" not in description and "var x" not in description


async def test_fetch_description_truncates_at_an_unclosed_style_tag():
    # job #2646 (Ziflow): a bare tag-strip left a whole CSS bundle as the
    # "description". The paired-tag regex fixed the well-formed case, but a
    # malformed page with NO matching </style> anywhere lets the regex's
    # non-greedy .*?</\1> simply fail to match — the tag and everything after
    # it survive untouched. Measured by direct execution before this fix.
    html_page = "<div>Real desc before</div><style>.a{color:red}<p>unreliable tail</p>"
    response = MagicMock(status_code=200, text=html_page)
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    cls = MagicMock()
    cls.return_value.__aenter__ = AsyncMock(return_value=client)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", cls):
        description, error = await fetch_description("https://example.com/job")
    assert error is None
    assert description == "Real desc before"
    assert "color" not in description


async def test_fetch_description_truncates_at_an_unclosed_script_tag():
    html_page = "<div>Real desc</div><script>var x = 1;<p>tail</p>"
    response = MagicMock(status_code=200, text=html_page)
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    cls = MagicMock()
    cls.return_value.__aenter__ = AsyncMock(return_value=client)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", cls):
        description, error = await fetch_description("https://example.com/job")
    assert error is None
    assert description == "Real desc"


async def test_fetch_description_reports_a_non_200_instead_of_guessing():
    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=404, text=""))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.core.posting.httpx.AsyncClient", return_value=client):
        text, error = await fetch_description("https://x.com/job")
    assert text is None
    assert "HTTP 404" in (error or "")


def test_strip_tags_is_public_so_other_packages_can_import_it_directly():
    # discovery/sources/http.py imports this across a package boundary; a
    # leading underscore would make that a private-symbol reach-in.
    assert strip_tags("<p>Hello  world</p>") == "Hello world"
    assert strip_tags("  ") is None
