"""Remotive asks for no category unless the profile's config names one (#120)."""

from unittest.mock import AsyncMock, patch

from moonlighter.discovery.portals import scan_portals
from moonlighter.discovery.sources.job_feeds.remotive import RemotiveScanner


async def test_remotive_asks_for_no_category_unless_configured():
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exit_arguments):
            return False

    urls = []

    async def fake_get_json(client, url):
        urls.append(url)
        return {"jobs": []}

    with (
        patch(
            "moonlighter.discovery.sources.job_feeds.remotive.httpx.AsyncClient",
            return_value=Client(),
        ),
        patch("moonlighter.discovery.sources.job_feeds.remotive.get_json", fake_get_json),
    ):
        await RemotiveScanner().scan()
        await RemotiveScanner().scan(category="customer-support")
        await RemotiveScanner().scan(category="data & ai")
    assert urls == [
        "https://remotive.com/api/remote-jobs",
        "https://remotive.com/api/remote-jobs?category=customer-support",
        "https://remotive.com/api/remote-jobs?category=data%20%26%20ai",
    ]
    assert "software-dev" not in RemotiveScanner.BASE


async def test_remotive_dispatch_passes_the_configured_category():
    with patch("moonlighter.discovery.portals.RemotiveScanner") as mock_scanner:
        mock_scanner.return_value.scan = AsyncMock(return_value=[])
        await scan_portals({"scan_remotive": True, "remotive_category": "design"}, {}, "")
    mock_scanner.return_value.scan.assert_awaited_once_with(category="design", stats={})
