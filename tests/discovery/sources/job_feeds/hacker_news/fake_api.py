"""The fake HN API (base URL, per-URL responses and client) shared by the HN tests."""

from unittest.mock import AsyncMock, MagicMock


def make_hn_client(url_map):
    """Branches on exact URL match (HN's API is one-resource-per-URL, no
    query params to substring-match on)."""

    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        if url in url_map:
            mock_response.status_code = 200
            mock_response.json.return_value = url_map[url]
        else:
            mock_response.status_code = 404
            mock_response.json.return_value = None
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


HN_BASE = "https://hacker-news.firebaseio.com/v0"


def hn_url_map(*, thread_id=100, kids=(201, 202, 203)):
    return {
        f"{HN_BASE}/user/whoishiring.json": {"submitted": [99, thread_id]},
        f"{HN_BASE}/item/99.json": {"id": 99, "title": "Ask HN: Freelancer? Seeking freelancer?"},
        f"{HN_BASE}/item/{thread_id}.json": {
            "id": thread_id,
            "title": "Ask HN: Who is hiring? (July 2026)",
            "kids": list(kids),
        },
        f"{HN_BASE}/item/201.json": {
            "id": 201,
            "text": "Acme | Remote | Full-time&lt;p&gt;Build things.&lt;/p&gt;",
        },
        f"{HN_BASE}/item/202.json": {
            "id": 202,
            "text": "No separator in this first line at all just prose",
        },
        f"{HN_BASE}/item/203.json": {"id": 203, "deleted": True, "text": "gone"},
    }
