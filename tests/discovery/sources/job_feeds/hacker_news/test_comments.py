"""How the HN scanner fetches a thread's comments and drops the deleted, failed and empty ones."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from moonlighter.discovery.sources.job_feeds.hacker_news import HNWhoIsHiringScanner

from tests.discovery.sources.job_feeds.hacker_news.fake_api import (
    HN_BASE,
    hn_url_map,
    make_hn_client,
)


async def test_hn_scan_skips_deleted_comments():
    mock_client = make_hn_client(hn_url_map())
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    assert all(not scanned_job.url.endswith("id=203") for scanned_job in jobs)


async def test_hn_fetch_kids_non_200_returns_empty():
    """The first call to /item/100.json (inside _find_latest_thread, checking
    the title) must succeed; the SECOND call to that same URL (inside
    _fetch_kids) is what returns non-200.
    """

    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        if url == f"{HN_BASE}/user/whoishiring.json":
            mock_response.status_code = 200
            mock_response.json.return_value = {"submitted": [100]}
            return mock_response
        if url == f"{HN_BASE}/item/100.json":
            if not getattr(fake_get, "_seen", False):
                fake_get._seen = True
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "id": 100,
                    "title": "Ask HN: Who is hiring? (July 2026)",
                }
                return mock_response
            mock_response.status_code = 500
            mock_response.json.return_value = None
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
    assert jobs == []


async def test_hn_fetch_kids_exception_returns_empty():
    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        if url == f"{HN_BASE}/user/whoishiring.json":
            mock_response.status_code = 200
            mock_response.json.return_value = {"submitted": [100]}
            return mock_response
        if url == f"{HN_BASE}/item/100.json":
            # First call (thread-title lookup, inside _find_latest_thread)
            # must succeed; the SECOND call to the same URL (_fetch_kids)
            # is what raises.
            if not getattr(fake_get, "_seen", False):
                fake_get._seen = True
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "id": 100,
                    "title": "Ask HN: Who is hiring? (July 2026)",
                }
                return mock_response
            raise httpx.ConnectError("boom")
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
    assert jobs == []


async def test_hn_fetch_comment_non_200_is_dropped():
    url_map = hn_url_map(kids=(201,))
    del url_map[f"{HN_BASE}/item/201.json"]  # 201 now 404s -> comment dropped
    mock_client = make_hn_client(url_map)
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_fetch_comment_exception_is_dropped():
    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        if url == f"{HN_BASE}/item/201.json":
            raise httpx.ConnectError("boom")
        base_map = hn_url_map(kids=(201,))
        if url in base_map:
            mock_response.status_code = 200
            mock_response.json.return_value = base_map[url]
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
    assert jobs == []


async def test_hn_comment_with_empty_text_is_dropped():
    url_map = hn_url_map(kids=(201,))
    url_map[f"{HN_BASE}/item/201.json"] = {"id": 201, "text": ""}
    mock_client = make_hn_client(url_map)
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_comment_with_only_tags_strips_to_empty_and_is_dropped():
    url_map = hn_url_map(kids=(201,))
    url_map[f"{HN_BASE}/item/201.json"] = {"id": 201, "text": "<p></p>"}
    mock_client = make_hn_client(url_map)
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []
