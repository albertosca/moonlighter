"""HTTP plumbing shared by every board fetch and by the posting reader.

Pure httpx + shapes, no models.
"""

from typing import Any

import httpx

HEADERS = {"User-Agent": "moonlighter/0.1"}


class FetchError(Exception):
    """A board fetch that failed: network error, non-200, non-JSON, wrong shape."""


async def get_json(
    client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None
) -> Any:
    """GET + JSON-decode, raising FetchError on any failure.

    It raises instead of returning a shape the caller must remember to test. The
    raise is what keeps a dead API distinguishable from a company with no openings
    (the Ashby lesson).
    """
    try:
        response = await client.get(url, headers=headers or HEADERS)
    except Exception as error:
        raise FetchError(f"{type(error).__name__}: {error}") from error
    if response.status_code != httpx.codes.OK:
        raise FetchError(f"HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as error:
        raise FetchError("non-JSON response") from error


def require_dict(data: Any) -> dict[str, Any]:
    """The JSON payload's top-level shape, or FetchError.

    The one-line check six scanners repeated after get_json (an API redesign, or
    an error page that decodes as a JSON string instead of the expected object,
    must not reach .get() and silently return nothing; it must be a visible scan
    error, the same reasoning get_json's own docstring gives).
    """
    if not isinstance(data, dict):
        raise FetchError("unexpected payload shape")
    return data
