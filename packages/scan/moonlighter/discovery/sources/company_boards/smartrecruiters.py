"""SmartRecruiters job boards: the paginated postings list, then one detail call per posting."""

import asyncio
import re
from typing import Any, override

import httpx

from moonlighter.core.web.http_fetch import FetchError, get_json, require_dict
from moonlighter.discovery.sources.base import BaseScanner, RawJob, normalize_remote_type
from moonlighter.discovery.sources.company_boards.gathering import gather_jobs


class SmartRecruitersScanner(BaseScanner):
    LIST = "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}"
    DETAIL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings/{pid}"
    APPLY = "https://jobs.smartrecruiters.com/{slug}/{pid}"

    @override
    async def scan(self, company_slugs: list[str], **keyword_arguments: Any) -> list[RawJob]:
        return await gather_jobs(
            "smartrecruiters", company_slugs, self._fetch, stats=keyword_arguments.get("stats")
        )

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        postings = await self._list(client, slug)
        jobs = []
        for posting in postings:
            posting_id, title = posting.get("id"), posting.get("name")
            if not posting_id or not title:
                continue
            place = posting.get("location") or {}
            location = self._location(place)
            remote_type = self._remote_type(place, location)
            description = await self._detail(client, slug, posting_id)
            jobs.append(
                RawJob(
                    source="smartrecruiters",
                    company=slug,
                    title=title,
                    url=self.APPLY.format(slug=slug, pid=posting_id),
                    location=location,
                    remote_type=remote_type,
                    description=description,
                )
            )
        return jobs

    @staticmethod
    def _location(place: dict[str, Any]) -> str | None:
        return ", ".join(part for part in (place.get("city"), place.get("country")) if part) or None

    @staticmethod
    def _remote_type(place: dict[str, Any], location: str | None) -> str | None:
        return (
            "remote"
            if place.get("remote")
            else "hybrid"
            if place.get("hybrid")
            else normalize_remote_type(location)
        )

    async def _list(self, client: httpx.AsyncClient, slug: str) -> list[dict[str, Any]]:
        postings: list[dict[str, Any]] = []
        offset = 0
        while True:
            data = require_dict(await get_json(client, self.LIST.format(slug=slug, offset=offset)))
            content = data.get("content") or []
            postings.extend(content)
            total = data.get("totalFound", 0)
            offset += len(content)
            if offset >= total or not content:
                return postings

    async def _detail(self, client: httpx.AsyncClient, slug: str, posting_id: str) -> str | None:
        await asyncio.sleep(0.1)
        try:
            data = await get_json(client, self.DETAIL.format(slug=slug, pid=posting_id))
        except FetchError:
            return None
        if not isinstance(data, dict):
            return None
        sections = (data.get("jobAd") or {}).get("sections") or {}
        parts = [
            section.get("text", "") for section in sections.values() if isinstance(section, dict)
        ]
        raw = " ".join(part for part in parts if part)
        return re.sub(r"<[^>]+>", " ", raw).strip() or None if raw else None
