"""Gupy's portal-wide keyword search across every company hosted on Gupy."""

import re
from typing import Any, override

import httpx

from moonlighter.core.http_fetch import FetchError, get_json
from moonlighter.core.log import get_logger
from moonlighter.discovery.sources.base import (
    BaseScanner,
    RawJob,
    ScanStats,
    SourceStats,
    normalize_remote_type,
)

logger = get_logger(__name__)


class GupyScanner(BaseScanner):
    """Gupy is a portal-wide keyword feed, not a per-company board.

    One global search across all companies hosted on Gupy -- so unlike the
    other HTTP scanners it is keyword-driven and builds its own client rather
    than routing through gather_jobs(slugs). Not registered in SOURCES;
    dispatched separately (mirrors the LinkedIn model) and gated behind a config
    flag in service.py.
    """

    BASE = "https://employability-portal.gupy.io/api/v1/jobs?jobName={kw}&limit={limit}&offset={offset}"

    @override
    async def scan(
        self,
        company_slugs: list[str] | None = None,
        *,
        keywords: str = "",
        **keyword_arguments: Any,
    ) -> list[RawJob]:
        stats: ScanStats | None = keyword_arguments.get("stats")
        async with httpx.AsyncClient(timeout=15) as client:
            jobs, errors = await self._fetch_pages(client, keywords)
        if stats is not None:
            stats["gupy"] = SourceStats(companies=0, jobs=len(jobs), errors=errors)
        return jobs

    async def _fetch_pages(
        self, client: httpx.AsyncClient, keywords: str
    ) -> tuple[list[RawJob], int]:
        jobs: list[RawJob] = []
        offset = 0
        while True:
            try:
                data = await get_json(
                    client, self.BASE.format(kw=keywords, limit=100, offset=offset)
                )
            except FetchError as error:
                logger.warning("[gupy] fetch failed: %s", error, exc_info=True)
                return jobs, 1
            if not isinstance(data, dict):
                return jobs, 1
            page = data.get("data") or []
            jobs.extend(self._jobs_from_page(page))
            # Advance by the actual page length (never by the server-reported
            # `limit`, which can legitimately be 0 and spin the loop forever --
            # the same bug just fixed for SmartRecruiters).
            offset += len(page)
            total = (data.get("pagination") or {}).get("total", 0)
            if not page or offset >= total:
                return jobs, 0

    @classmethod
    def _jobs_from_page(scanner_class, page: list[dict[str, Any]]) -> list[RawJob]:
        return [job for item in page if (job := scanner_class._job_from_item(item)) is not None]

    @staticmethod
    def _job_from_item(item: dict[str, Any]) -> RawJob | None:
        title, url = item.get("name"), item.get("jobUrl")
        if not title or not url:
            return None
        location = (
            ", ".join(
                part for part in (item.get("city"), item.get("state"), item.get("country")) if part
            )
            or None
        )
        remote_type = (
            "remote"
            if item.get("isRemoteWork")
            else normalize_remote_type(item.get("workplaceType"))
        )
        raw = (item.get("description") or "").replace("&nbsp;", " ")
        description = re.sub(r"<[^>]+>", " ", raw).strip() if raw else None
        return RawJob(
            source="gupy",
            company=item.get("careerPageName") or "gupy",
            title=title,
            url=url,
            location=location,
            remote_type=remote_type,
            description=description,
        )
