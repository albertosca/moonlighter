"""We Work Remotely reads the all-jobs feed unless the config names a category (#120)."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.discovery.portals import scan_portals
from moonlighter.discovery.sources.job_feeds.weworkremotely import WeWorkRemotelyScanner


async def test_wwr_reads_the_all_jobs_feed_unless_a_category_is_configured():
    fetched = []

    async def fake_get(url, **_keyword_arguments):
        fetched.append(url)
        response = MagicMock()
        response.status_code = 200
        response.text = "<rss><channel></channel></rss>"
        return response

    client = MagicMock()
    client.get = fake_get
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
        return_value=client,
    ):
        await WeWorkRemotelyScanner().scan()
        await WeWorkRemotelyScanner().scan(category="design")
        await WeWorkRemotelyScanner().scan(category="../x")
    assert fetched == [
        "https://weworkremotely.com/remote-jobs.rss",
        "https://weworkremotely.com/categories/remote-design-jobs.rss",
        "https://weworkremotely.com/categories/remote-..%2Fx-jobs.rss",
    ]
    assert "programming" not in WeWorkRemotelyScanner.BASE


async def test_wwr_dispatch_passes_the_configured_category():
    with patch("moonlighter.discovery.portals.WeWorkRemotelyScanner") as mock_scanner:
        mock_scanner.return_value.scan = AsyncMock(return_value=[])
        await scan_portals({"scan_wwr": True, "wwr_category": "design"}, {}, "")
    mock_scanner.return_value.scan.assert_awaited_once_with(category="design", stats={})
