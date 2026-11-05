"""Remotive's portal-wide remote-jobs feed, optionally narrowed to one category."""

from typing import Any, override
from urllib.parse import quote

import httpx

from moonlighter.core.log import get_logger
from moonlighter.core.web.http_fetch import FetchError, get_json
from moonlighter.core.web.posting import normalize_feed_description
from moonlighter.discovery.sources.base import BaseScanner, RawJob, ScanStats, SourceStats

logger = get_logger(__name__)


class RemotiveScanner(BaseScanner):
    """Remotive is a portal-wide remote-jobs board like RemoteOKScanner.

    Not registered in SOURCES, dispatched separately in portals.py, gated
    behind a config flag (off by default).

    ToS note: max 4 requests/day, must link back to Remotive as source. No
    rate-limiter here (no precedent for one in this codebase) -- the config
    flag is the control point; whoever enables this scanner is responsible
    for not scanning more than a few times a day.
    """

    BASE = "https://remotive.com/api/remote-jobs"

    @override
    async def scan(
        self, company_slugs: list[str] | None = None, **keyword_arguments: Any
    ) -> list[RawJob]:
        stats: ScanStats | None = keyword_arguments.get("stats")
        category = keyword_arguments.get("category")
        # No category configured: every category, narrowed afterwards by the title
        # keywords. Never a built-in profession.
        feed_url = f"{self.BASE}?category={quote(str(category))}" if category else self.BASE
        data, errors = await self._fetch_postings(feed_url)
        jobs: list[RawJob] = []
        for item in data.get("jobs") or []:
            title, url = item.get("title"), item.get("url")
            if not title or not url:
                continue
            jobs.append(
                RawJob(
                    source="remotive",
                    company=item.get("company_name") or "Remotive",
                    title=title,
                    url=url,
                    location=item.get("candidate_required_location") or None,
                    remote_type="remote",
                    description=normalize_feed_description(item.get("description") or ""),
                )
            )
        if stats is not None:
            stats["remotive"] = SourceStats(companies=0, jobs=len(jobs), errors=errors)
        return jobs

    @staticmethod
    async def _fetch_postings(url: str) -> tuple[dict[str, Any], int]:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                data = await get_json(client, url)
            except FetchError as error:
                logger.warning("[remotive] fetch failed: %s", error, exc_info=True)
                return {}, 1
        if not isinstance(data, dict):
            # A shape change is an error, not a silent zero.
            return {}, 1
        return data, 0
