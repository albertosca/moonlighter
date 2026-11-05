"""SmartRecruiters list and detail payloads and the fake clients that serve them."""

from unittest.mock import AsyncMock, MagicMock

SR_LIST_P1 = {
    "offset": 0,
    "limit": 1,
    "totalFound": 2,
    "content": [
        {
            "id": "744000000000001",
            "uuid": "u1",
            "name": "SRE",
            "location": {"city": "Remote", "country": "US", "remote": True, "hybrid": False},
        }
    ],
}


SR_DETAIL = {"jobAd": {"sections": {"jobDescription": {"text": "<p>Own the pipeline</p>"}}}}


def sr_response(payload, status_code=200):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = payload
    return mock_response


def make_url_branching_client(url_map):
    """A mock client whose .get(url) branches on a substring match in url_map.

    url_map: dict[str substring -> response payload]. Raises AssertionError on a URL
    that matches no substring, so a test with an unexpected call fails loudly instead
    of silently succeeding.
    """

    async def fake_get(url, headers=None):
        for substring, payload in url_map.items():
            if substring in url:
                return sr_response(payload)
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client
