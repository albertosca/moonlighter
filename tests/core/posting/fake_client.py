"""The fake httpx.AsyncClient the ATS tests share: a class to patch in, and the client it yields, whose every GET answers 200 with one JSON payload."""

from unittest.mock import AsyncMock, MagicMock


def fake_client(response_json):
    response = MagicMock(status_code=200)
    response.json.return_value = response_json
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client_class = MagicMock()
    client_class.return_value.__aenter__ = AsyncMock(return_value=client)
    client_class.return_value.__aexit__ = AsyncMock(return_value=False)
    return client_class, client
