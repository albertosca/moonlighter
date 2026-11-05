"""How the HN scanner finds the latest 'Who is hiring?' thread, and what it sends while looking."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from moonlighter.core.web.http_fetch import HEADERS
from moonlighter.discovery.sources.job_feeds.hacker_news import HNWhoIsHiringScanner
from tests.discovery.sources.job_feeds.hacker_news.fake_api import (
    HN_BASE,
    hn_url_map,
    make_hn_client,
)


async def test_hn_no_who_is_hiring_thread_found_returns_empty():
    url_map = {
        f"{HN_BASE}/user/whoishiring.json": {"submitted": [99]},
        f"{HN_BASE}/item/99.json": {"id": 99, "title": "Ask HN: Freelancer? Seeking freelancer?"},
    }
    mock_client = make_hn_client(url_map)
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_thread_with_no_kids_returns_empty():
    url_map = {
        f"{HN_BASE}/user/whoishiring.json": {"submitted": [100]},
        f"{HN_BASE}/item/100.json": {"id": 100, "title": "Ask HN: Who is hiring? (July 2026)"},
    }
    mock_client = make_hn_client(url_map)
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_network_exception_on_user_lookup_returns_empty():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_user_lookup_non_200_returns_empty():
    mock_client = make_hn_client({})  # every URL 404s
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_thread_lookup_skips_item_non_200_and_continues():
    url_map = {
        f"{HN_BASE}/user/whoishiring.json": {"submitted": [98, 100]},
        # 98 is the first candidate but its own item fetch 404s -- loop must
        # continue to 100 rather than stopping.
        f"{HN_BASE}/item/100.json": {
            "id": 100,
            "title": "Ask HN: Who is hiring? (July 2026)",
            "kids": [201],
        },
        f"{HN_BASE}/item/201.json": {"id": 201, "text": "Acme | Remote"},
    }
    mock_client = make_hn_client(url_map)
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    assert len(jobs) == 1
    assert jobs[0].company == "Acme"


async def test_hn_thread_lookup_skips_item_exception_and_continues():
    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        if url == f"{HN_BASE}/user/whoishiring.json":
            mock_response.status_code = 200
            mock_response.json.return_value = {"submitted": [98, 100]}
            return mock_response
        if url == f"{HN_BASE}/item/98.json":
            raise httpx.ConnectError("boom")
        if url == f"{HN_BASE}/item/100.json":
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": 100,
                "title": "Ask HN: Who is hiring? (July 2026)",
                "kids": [],
            }
            return mock_response
        mock_response.status_code = 404
        mock_response.json.return_value = None
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []  # thread found (id 100), but it has no kids


async def test_hn_sends_the_moonlighter_user_agent_on_every_request():
    mock_client = make_hn_client(hn_url_map())
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        await HNWhoIsHiringScanner().scan()
    requests = mock_client.get.await_args_list
    assert requests
    assert [request.kwargs for request in requests] == [{"headers": HEADERS}] * len(requests)


async def test_hn_thread_search_looks_at_the_ten_latest_submissions_only():
    ten_latest_submissions = {
        f"{HN_BASE}/item/{item_id}.json": {
            "id": item_id,
            "title": "Ask HN: Freelancer? Seeking freelancer?",
        }
        for item_id in range(1, 11)
    }
    url_map = {
        f"{HN_BASE}/user/whoishiring.json": {"submitted": list(range(1, 12))},
        **ten_latest_submissions,
        f"{HN_BASE}/item/11.json": {
            "id": 11,
            "title": "Ask HN: Who is hiring? (June 2026)",
            "kids": [201],
        },
        f"{HN_BASE}/item/201.json": {"id": 201, "text": "Acme | Remote | Full-time"},
    }
    mock_client = make_hn_client(url_map)
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []
    requested_urls = [request.args[0] for request in mock_client.get.await_args_list]
    assert f"{HN_BASE}/item/11.json" not in requested_urls
