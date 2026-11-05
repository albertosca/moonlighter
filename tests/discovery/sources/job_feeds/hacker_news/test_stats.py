"""How the HN scanner counts its jobs and errors in the scan stats."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moonlighter.discovery.sources.base import ScanStats, SourceStats
from moonlighter.discovery.sources.job_feeds.hacker_news import HNWhoIsHiringScanner
from tests.discovery.sources.fake_http_clients import mock_client_class
from tests.discovery.sources.job_feeds.hacker_news.fake_api import hn_url_map, make_hn_client


@pytest.mark.asyncio
async def test_hn_records_stats_on_failure_when_no_thread_found():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(status_code=503))
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        stats: ScanStats = {}
        jobs = await HNWhoIsHiringScanner().scan(stats=stats)
    assert jobs == []
    assert stats["hn_whoishiring"] == SourceStats(companies=0, jobs=0, errors=1)


@pytest.mark.asyncio
async def test_hn_records_stats_on_success():
    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        url_map = hn_url_map()
        if url in url_map:
            mock_response.status_code = 200
            mock_response.json.return_value = url_map[url]
        else:
            mock_response.status_code = 404
            mock_response.json.return_value = None
        return mock_response

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    with patch("httpx.AsyncClient", mock_client_class(mock_client)):
        stats: ScanStats = {}
        jobs = await HNWhoIsHiringScanner().scan(stats=stats)
    assert stats["hn_whoishiring"].jobs == len(jobs) > 0
    # kid 203 is a deleted comment (dropped, not an error); kid 202 has no
    # separator and falls back to the prose title (also not an error) -- only
    # a genuine fetch/parse failure should count.
    assert stats["hn_whoishiring"].errors == 0


@pytest.mark.asyncio
async def test_hn_records_stats_counts_comment_gather_exceptions():
    """_fetch_comment already swallows its own network/HTTP failures into None
    (a 404'd or dead comment is indistinguishable and not an error, per the
    brief) -- but asyncio.gather(return_exceptions=True) can still surface a
    genuine Exception object if something above that try/except blows up.
    That's what the error-counting formula is for; force one here directly.
    """
    url_map = hn_url_map(kids=(201, 202))
    mock_client = make_hn_client(url_map)
    with (
        patch("httpx.AsyncClient", mock_client_class(mock_client)),
        patch.object(
            HNWhoIsHiringScanner,
            "_fetch_comment",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
    ):
        stats: ScanStats = {}
        jobs = await HNWhoIsHiringScanner().scan(stats=stats)
    assert jobs == []
    assert stats["hn_whoishiring"] == SourceStats(companies=0, jobs=0, errors=2)


async def test_hn_comment_fetch_failures_count_as_errors_deleted_do_not():
    # A 404 on a comment used to flatten into the same None as a deleted
    # comment, so per-comment fetch failures never reached the stats.
    url_map = hn_url_map(kids=(201, 203, 999))  # 999 is absent -> 404
    mock_client = make_hn_client(url_map)
    stats = {}
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan(stats=stats)

    assert [scanned_job.company for scanned_job in jobs] == ["Acme"]
    source_stats = stats["hn_whoishiring"]
    assert source_stats.jobs == 1
    assert source_stats.errors == 1  # the 404; the deleted comment 203 is not an error
