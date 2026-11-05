"""get_json raises FetchError on every failed fetch; require_dict refuses a non-object payload."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from moonlighter.core.web.http_fetch import FetchError, get_json, require_dict


@pytest.mark.asyncio
async def test_get_json_raises_on_network_error():
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(FetchError):
        await get_json(client, "https://example.test/x")


@pytest.mark.asyncio
async def test_get_json_raises_on_non_200():
    client = AsyncMock()
    response = MagicMock(status_code=500)
    client.get = AsyncMock(return_value=response)
    with pytest.raises(FetchError, match="HTTP 500"):
        await get_json(client, "https://example.test/x")


@pytest.mark.asyncio
async def test_get_json_raises_on_non_json_body():
    client = AsyncMock()
    response = MagicMock(status_code=200)
    response.json.side_effect = ValueError("not json")
    client.get = AsyncMock(return_value=response)
    with pytest.raises(FetchError, match="non-JSON"):
        await get_json(client, "https://example.test/x")


def test_require_dict_returns_the_dict_unchanged():
    payload = {"jobs": []}
    assert require_dict(payload) is payload


def test_require_dict_raises_on_a_list():
    with pytest.raises(FetchError, match="unexpected payload shape"):
        require_dict([1, 2, 3])


def test_require_dict_raises_on_a_string():
    # Measured failure shape: an API returning an HTML error page as a 200
    # decodes as a JSON string, not a dict — the six scanners this helper
    # collapses all relied on this exact raise to turn that into a visible
    # scan error instead of an AttributeError on .get().
    with pytest.raises(FetchError, match="unexpected payload shape"):
        require_dict("<html>error</html>")


def test_require_dict_raises_on_none():
    with pytest.raises(FetchError, match="unexpected payload shape"):
        require_dict(None)
