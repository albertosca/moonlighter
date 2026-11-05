"""How the Recruitee scanner maps offers, resolves custom domains and survives failed responses."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from moonlighter.discovery.sources.company_boards.recruitee import RecruiteeScanner

from tests.discovery.sources.fake_http_clients import make_mock_client, mock_client_class

RECRUITEE_RESPONSE = {
    "offers": [
        {
            "title": "Backend Dev",
            "id": 42,
            "slug": "backend-dev",
            "careers_apply_url": "https://x.recruitee.com/o/backend-dev/c/new",
            "location": "Amsterdam, Netherlands",
            "remote": False,
            "description": "<ul><li>Go</li></ul>",
        }
    ]
}


async def test_recruitee_maps_fields_and_strips_html():
    mock_client = make_mock_client(RECRUITEE_RESPONSE)
    with patch(
        "moonlighter.discovery.sources.company_boards.recruitee.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert len(jobs) == 1
    scanned_job = jobs[0]
    assert scanned_job.source == "recruitee"
    assert scanned_job.company == "acme"
    assert scanned_job.title == "Backend Dev"
    assert scanned_job.url == "https://x.recruitee.com/o/backend-dev/c/new"
    assert scanned_job.location == "Amsterdam, Netherlands"
    assert (
        scanned_job.remote_type is None
    )  # remote False + bare city: unknown, never invented onsite
    assert scanned_job.description == "Go"


async def test_recruitee_remote_flag_true():
    response = {
        "offers": [
            {
                "title": "Eng",
                "careers_apply_url": "https://x.recruitee.com/o/eng/c/new",
                "location": "Anywhere",
                "remote": True,
            }
        ]
    }
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.recruitee.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs[0].remote_type == "remote"


async def test_recruitee_skips_entry_without_title():
    response = {"offers": [{"title": "", "careers_apply_url": ""}]}
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.recruitee.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_skips_entry_without_url():
    response = {"offers": [{"title": "Eng", "careers_apply_url": ""}]}
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.recruitee.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_500_response_skips_company():
    mock_client = make_mock_client({}, status_code=500)
    with patch(
        "moonlighter.discovery.sources.company_boards.recruitee.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_network_exception_skips_company():
    mock_client = make_mock_client(raise_exception=httpx.ConnectError("timeout"))
    with patch(
        "moonlighter.discovery.sources.company_boards.recruitee.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_non_dict_response_returns_empty():
    mock_client = make_mock_client([{"title": "Eng"}])
    with patch(
        "moonlighter.discovery.sources.company_boards.recruitee.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_missing_offers_key_returns_empty():
    mock_client = make_mock_client({"other": []})
    with patch(
        "moonlighter.discovery.sources.company_boards.recruitee.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_custom_domain_entry():
    """An entry containing a dot is a custom career domain. Live-verified
    2026-08-12: careers.tellent.com and jobs.channable.com serve the same
    /api/offers/ payload as {slug}.recruitee.com."""
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = RECRUITEE_RESPONSE
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok_response)
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        jobs = await RecruiteeScanner().scan(["jobs.channable.com"])
    assert len(jobs) > 0
    called_url = mock_client.get.call_args.args[0]
    assert called_url == "https://jobs.channable.com/api/offers/"
    assert jobs[0].company == "jobs.channable.com"


async def test_recruitee_slug_entry_unchanged():
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = RECRUITEE_RESPONSE
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok_response)
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        await RecruiteeScanner().scan(["acme"])
    assert mock_client.get.call_args.args[0] == "https://acme.recruitee.com/api/offers/"
