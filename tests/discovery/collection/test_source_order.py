"""collect_raw_jobs keeps its source order, its warning order and its wording."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.discovery.collection import collect_raw_jobs
from moonlighter.discovery.sources.base import RawJob, ScannerSessionExpiredError, SourceStats


@contextlib.contextmanager
def _patched_feeds(jobs_by_feed):
    """Replaces each portal feed scanner class with a mock whose scan() returns its jobs."""
    targets = {
        "gupy": "moonlighter.discovery.portals.GupyScanner",
        "remoteok": "moonlighter.discovery.portals.RemoteOKScanner",
        "remotive": "moonlighter.discovery.portals.RemotiveScanner",
        "wwr": "moonlighter.discovery.portals.WeWorkRemotelyScanner",
        "hn": "moonlighter.discovery.portals.HNWhoIsHiringScanner",
    }
    with contextlib.ExitStack() as stack:
        for feed, target in targets.items():
            feed_class = stack.enter_context(patch(target))
            feed_class.return_value.scan = AsyncMock(return_value=jobs_by_feed.get(feed, []))
        yield


class _PluginJobsScanner:
    """A browser-scanner plugin that returns one job."""

    def __init__(self, page):
        pass

    async def scan(self, **keyword_arguments):
        return [RawJob(source="plugin", company="P", title="Engineer", url="https://p.example/1")]


class _ExpiredSessionScanner:
    """A browser-scanner plugin whose login has expired."""

    def __init__(self, page):
        pass

    async def scan(self, **keyword_arguments):
        raise ScannerSessionExpiredError("session expired")


async def _collect_with_every_source(keywords, config):
    async def http_scan(slugs, *, stats):
        stats["ashby"] = SourceStats(companies=1, jobs=1, errors=1)
        return [
            RawJob(
                source="ashby",
                company="H",
                title="Engineer",
                url="https://x.recruitee.com/o/dev/c/new",
            )
        ]

    http_scanner = MagicMock()
    http_scanner.scan = http_scan
    feed_jobs = {
        feed: [RawJob(source=feed, company="F", title="Engineer", url=f"https://{feed}.example/1")]
        for feed in ("gupy", "remoteok", "remotive", "wwr", "hn")
    }
    with (
        patch(
            "moonlighter.discovery.collection.build_http_scanners",
            return_value={"ashby": http_scanner},
        ),
        patch(
            "moonlighter.discovery.collection.discover_entry_points",
            return_value=[_PluginJobsScanner, _ExpiredSessionScanner],
        ),
        patch("moonlighter.core.browser", create=True) as mock_browser,
        _patched_feeds(feed_jobs),
    ):
        mock_browser.new_page = AsyncMock(return_value=AsyncMock())
        return await collect_raw_jobs(keywords, config, {"ashby": ["acme"], "workday": ["acme"]})


_EVERY_FEED_ON = {
    "scan_gupy": True,
    "scan_remoteok": True,
    "scan_remotive": True,
    "scan_wwr": True,
    "scan_hn_whoishiring": True,
}


async def test_collect_raw_jobs_orders_sources_and_normalises_urls():
    raw_jobs, _ = await _collect_with_every_source("engineer", _EVERY_FEED_ON)
    assert [raw_job.url for raw_job in raw_jobs] == [
        "https://x.recruitee.com/o/dev",
        "https://p.example/1",
        "https://gupy.example/1",
        "https://remoteok.example/1",
        "https://remotive.example/1",
        "https://wwr.example/1",
        "https://hn.example/1",
    ]


async def test_collect_raw_jobs_warnings_keep_their_wording_and_order():
    raw_jobs, warning = await _collect_with_every_source("", _EVERY_FEED_ON)
    assert warning == (
        "⚠️  company_list.yaml: unknown source 'workday' — no scanner with that name, "
        "entries ignored\n"
        "⚠️  _ExpiredSession: session expired\n"
        "⚠️  scan_gupy is on but no keywords were given: Gupy is a keyword feed and "
        "moonlighter has no built-in search term, so it was skipped. Pass keywords.\n"
        "⚠️  ashby: 1 jobs from 1 company (1 fetch error)"
    )
    assert [raw_job.source for raw_job in raw_jobs] == [
        "ashby",
        "plugin",
        "remoteok",
        "remotive",
        "wwr",
        "hn",
    ]
