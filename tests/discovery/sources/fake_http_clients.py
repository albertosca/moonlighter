"""Fake httpx clients shared by the source tests: one response, one payload, or a client class."""

import json
from unittest.mock import AsyncMock, MagicMock


def make_mock_client(response_json=None, status_code=200, raise_exception=None):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = status_code
    if response_json is not None:
        mock_response.json.return_value = response_json

    if raise_exception:
        mock_client.get = AsyncMock(side_effect=raise_exception)
        mock_client.post = AsyncMock(side_effect=raise_exception)
    else:
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response)

    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def make_simple_client(payload, status=200):
    """Single-GET JSON mock client — for scanners that don't paginate."""

    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        mock_response.status_code = status
        mock_response.json.return_value = payload
        mock_response.text = json.dumps(payload) if not isinstance(payload, str) else payload
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def mock_client_class(mock_client):
    client_class = MagicMock()
    client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    client_class.return_value.__aexit__ = AsyncMock(return_value=False)
    return client_class
