"""WeWorkRemotely's portal-wide RSS feed, optionally narrowed to one category."""

import contextlib
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, override
from urllib.parse import quote
from xml.etree.ElementTree import Element, ParseError, fromstring

import httpx

from moonlighter.core.http_fetch import HEADERS
from moonlighter.core.log import get_logger
from moonlighter.core.posting import normalize_feed_description
from moonlighter.discovery.sources.base import BaseScanner, RawJob, ScanStats, SourceStats

logger = get_logger(__name__)


class WeWorkRemotelyScanner(BaseScanner):
    """WeWorkRemotely is a portal-wide RSS feed, like RemoteOKScanner.

    Not registered in SOURCES, dispatched separately in service.py, gated
    behind a config flag (off by default).
    """

    BASE = "https://weworkremotely.com/remote-jobs.rss"
    CATEGORY_URL = "https://weworkremotely.com/categories/remote-{category}-jobs.rss"

    @override
    async def scan(
        self, company_slugs: list[str] | None = None, **keyword_arguments: Any
    ) -> list[RawJob]:
        stats: ScanStats | None = keyword_arguments.get("stats")
        body, errors = await self._fetch_feed(self._feed_url(keyword_arguments.get("category")))
        root = None
        if body:
            root = self._parse_feed(body)
            if root is None:
                errors = errors or 1
        jobs = self._jobs_from_feed(root) if root is not None else []
        if stats is not None:
            stats["weworkremotely"] = SourceStats(companies=0, jobs=len(jobs), errors=errors)
        return jobs

    def _feed_url(self, category: object) -> str:
        # No category configured: the all-jobs feed, narrowed afterwards by the title
        # keywords. Never a built-in profession.
        return (
            self.CATEGORY_URL.format(category=quote(str(category), safe=""))
            if category
            else self.BASE
        )

    @staticmethod
    async def _fetch_feed(url: str) -> tuple[str, int]:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                http_response = await client.get(url, headers=HEADERS)
            except Exception as error:
                logger.warning("[weworkremotely] fetch failed: %s", error, exc_info=True)
                return "", 1
            if http_response.status_code != httpx.codes.OK:
                logger.warning("[weworkremotely] fetch failed: HTTP %s", http_response.status_code)
                return "", 1
            return http_response.text, 0

    @staticmethod
    def _parse_feed(body: str) -> Element | None:
        try:
            # S314: stdlib ElementTree parses untrusted network data (the RSS
            # feed is external, fetched over the network). Accepted: Python's
            # ElementTree does not resolve external entities/DTDs by default
            # (unlike some other XML parsers), so the residual risk is
            # entity-expansion DoS (e.g. "billion laughs"), not XXE file
            # disclosure -- a local nuisance (this call briefly hangs), not a
            # security breach, for a single-user local tool. No new
            # dependency (defusedxml) added for this; revisit if that
            # tradeoff changes.
            root = fromstring(body)  # noqa: S314 - accepted risk, see the comment above: no external entities, only a local expansion DoS
        except ParseError as error:
            logger.warning("[weworkremotely] malformed feed: %s", error, exc_info=True)
            return None
        return root

    @classmethod
    def _jobs_from_feed(scanner_class, root: Element) -> list[RawJob]:
        jobs = []
        for item in root.findall(".//item"):
            raw_title = (item.findtext("title") or "").strip()
            url = (item.findtext("link") or "").strip()
            if not raw_title or not url:
                continue
            company, title = scanner_class._company_and_title(raw_title)
            jobs.append(
                RawJob(
                    source="weworkremotely",
                    company=company,
                    title=title,
                    url=url,
                    location=(item.findtext("region") or "").strip() or None,
                    remote_type="remote",
                    description=normalize_feed_description(item.findtext("description") or ""),
                    posted_at=scanner_class._published_at(item.findtext("pubDate")),
                )
            )
        return jobs

    @staticmethod
    def _company_and_title(raw_title: str) -> tuple[str, str]:
        if ":" in raw_title:
            company, _, position = raw_title.partition(":")
            return company.strip(), position.strip()
        return "WeWorkRemotely", raw_title

    @staticmethod
    def _published_at(pub_date: str | None) -> datetime | None:
        posted_at = None
        if pub_date:
            with contextlib.suppress(Exception):
                posted_at = parsedate_to_datetime(pub_date)
        return posted_at
