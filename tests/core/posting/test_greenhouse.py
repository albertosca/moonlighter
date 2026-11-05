"""A Greenhouse job URL is read through the board API (unescaped content, company, title and location), and a failed or non-dict answer returns None."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.core.posting import FetchedPosting, fetch_posting_via_ats

from tests.core.posting.fake_client import fake_client

GREENHOUSE_JOB = {
    "title": "Account Executive",
    "company_name": "GitLab",
    # Live-verified 2026-08-12: the board API returns content HTML-entity-escaped.
    "content": "&lt;div&gt;&lt;p&gt;Build things.&lt;/p&gt;&lt;/div&gt;",
}


@pytest.mark.asyncio
async def test_greenhouse_url_routes_to_board_api():
    client_class, client = fake_client(GREENHOUSE_JOB)
    with patch("httpx.AsyncClient", client_class):
        posting = await fetch_posting_via_ats("https://boards.greenhouse.io/gitlab/jobs/8503792002")
    assert posting == FetchedPosting(
        company="GitLab", title="Account Executive", description="Build things."
    )
    assert (
        client.get.call_args.args[0]
        == "https://boards-api.greenhouse.io/v1/boards/gitlab/jobs/8503792002"
    )


@pytest.mark.asyncio
async def test_greenhouse_posting_carries_its_location():
    """add_job hands the location to the evaluator's regional filter; without it the
    LLM judges eligibility from the description alone (the 2026-08-21 gitlab class).
    """
    job = {**GREENHOUSE_JOB, "location": {"name": "Bangalore, India"}}
    client_class, _client_mock = fake_client(job)
    with patch("httpx.AsyncClient", client_class):
        posting = await fetch_posting_via_ats("https://boards.greenhouse.io/gitlab/jobs/8503792002")
    assert posting is not None
    assert posting.location == "Bangalore, India"
    assert posting.remote is False


@pytest.mark.asyncio
async def test_greenhouse_fetch_error_returns_none():
    """A non-200 from the board API (e.g. a stale/deleted job_id) is a FetchError,
    swallowed so the caller falls back to the generic HTML fetch.
    """
    response = MagicMock(status_code=404)
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client_class = MagicMock()
    client_class.return_value.__aenter__ = AsyncMock(return_value=client)
    client_class.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", client_class):
        posting = await fetch_posting_via_ats("https://boards.greenhouse.io/gitlab/jobs/8503792002")
    assert posting is None


@pytest.mark.asyncio
async def test_greenhouse_non_dict_response_returns_none():
    client_class, _client_mock = fake_client(["unexpected", "shape"])
    with patch("httpx.AsyncClient", client_class):
        posting = await fetch_posting_via_ats("https://boards.greenhouse.io/gitlab/jobs/8503792002")
    assert posting is None
