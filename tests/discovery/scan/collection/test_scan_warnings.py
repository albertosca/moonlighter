"""A dead or unknown source reaches the scan report as a warning."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.discovery.scan.collection import collect_raw_jobs

from tests.discovery.sources.fake_http_clients import mock_client_class


async def test_dead_api_reaches_the_scan_report():
    """CANARY: the exact dead-Ashby shape (HTTP 200, error payload, no jobs key)
    must surface in the user-visible report — this is the detector biting on the
    failure that actually happened, silently, for weeks.
    """
    dead = MagicMock(status_code=200)
    dead.json.return_value = {"errors": [{"message": "Cannot query field"}]}
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=dead)
    with (
        patch("httpx.AsyncClient", mock_client_class(mock_client)),
        patch("moonlighter.discovery.scan.collection.discover_entry_points", return_value=[]),
    ):
        raw_jobs, warning = await collect_raw_jobs("", {}, {"ashby": ["linear", "posthog"]})
    assert raw_jobs == []
    assert warning is not None
    assert "ashby: 0 jobs from 2 companies" in warning


async def test_unknown_company_list_source_warns():
    with patch("httpx.AsyncClient", mock_client_class(AsyncMock())):
        _, warning = await collect_raw_jobs("", {}, {"workday": ["acme"]})
    assert warning is not None
    assert "unknown source 'workday'" in warning
