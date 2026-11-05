"""RemoteOK's portal-wide remote-jobs feed."""

import re
from typing import Any, override

import httpx

from moonlighter.core.http_fetch import FetchError, get_json
from moonlighter.core.log import get_logger
from moonlighter.discovery.sources.base import BaseScanner, RawJob, ScanStats, SourceStats

logger = get_logger(__name__)


class RemoteOKScanner(BaseScanner):
    """RemoteOK is a portal-wide remote-jobs board (all companies, all categories).

    Like GupyScanner, it doesn't route through gather_jobs(slugs). Not
    registered in SOURCES; dispatched separately in service.py, gated behind a
    config flag (off by default).
    """

    BASE = "https://remoteok.com/api"

    @override
    async def scan(
        self, company_slugs: list[str] | None = None, **keyword_arguments: Any
    ) -> list[RawJob]:
        stats: ScanStats | None = keyword_arguments.get("stats")
        data, errors = await self._fetch_postings()
        jobs: list[RawJob] = []
        for item in data:
            title, url = item.get("position"), item.get("url")
            if not title or not url:
                continue
            jobs.append(
                RawJob(
                    source="remoteok",
                    company=item.get("company") or "RemoteOK",
                    title=title,
                    url=url,
                    location=item.get("location") or None,
                    remote_type="remote",
                    description=self._description(item.get("description") or ""),
                )
            )
        if stats is not None:
            stats["remoteok"] = SourceStats(companies=0, jobs=len(jobs), errors=errors)
        return jobs

    async def _fetch_postings(self) -> tuple[list[Any], int]:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                data = await get_json(client, self.BASE)
            except FetchError as error:
                logger.warning("[remoteok] fetch failed: %s", error, exc_info=True)
                return [], 1
        if not isinstance(data, list):
            # A shape change is an error, not a silent zero.
            return [], 1
        return data, 0

    @staticmethod
    def _description(raw_description: str) -> str | None:
        description = None
        if raw_description:
            description = re.sub(r"<[^>]+>", " ", raw_description).strip()
            description = re.sub(r"\s+", " ", description)
            description = re.sub(r"\s+([.!?,;:])", r"\1", description) or None
        return description
