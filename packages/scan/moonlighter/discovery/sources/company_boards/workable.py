"""Workable job boards, read through the public widget API."""

import re
from typing import Any, override

import httpx

from moonlighter.core.http_fetch import get_json, require_dict
from moonlighter.discovery.sources.base import BaseScanner, RawJob, normalize_remote_type
from moonlighter.discovery.sources.company_boards.gathering import gather_jobs


class WorkableScanner(BaseScanner):
    BASE = "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"

    @override
    async def scan(self, company_slugs: list[str], **keyword_arguments: Any) -> list[RawJob]:
        return await gather_jobs(
            "workable", company_slugs, self._fetch, stats=keyword_arguments.get("stats")
        )

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        data = require_dict(await get_json(client, self.BASE.format(slug=slug)))
        jobs = []
        for item in data.get("jobs", []):
            title, url = item.get("title"), item.get("application_url")
            if not title or not url:
                continue
            location = (
                ", ".join(
                    part
                    for part in (item.get("city"), item.get("state"), item.get("country"))
                    if part
                )
                or None
            )
            remote_type = "remote" if item.get("telecommuting") else normalize_remote_type(location)
            raw = item.get("description") or ""
            description = re.sub(r"<[^>]+>", " ", raw).strip() if raw else None
            jobs.append(
                RawJob(
                    source="workable",
                    company=slug,
                    title=title,
                    url=url,
                    location=location,
                    remote_type=remote_type,
                    description=description,
                )
            )
        return jobs
