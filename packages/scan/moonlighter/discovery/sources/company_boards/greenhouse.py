"""Greenhouse job boards, read through the public boards API."""

import contextlib
import re
from datetime import datetime
from typing import Any, override

import httpx

from moonlighter.core.http_fetch import get_json, require_dict
from moonlighter.discovery.sources.base import BaseScanner, RawJob, normalize_remote_type
from moonlighter.discovery.sources.company_boards.gathering import gather_jobs


class GreenhouseScanner(BaseScanner):
    BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

    @override
    async def scan(self, company_slugs: list[str], **keyword_arguments: Any) -> list[RawJob]:
        return await gather_jobs(
            "greenhouse", company_slugs, self._fetch, stats=keyword_arguments.get("stats")
        )

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        data = require_dict(await get_json(client, self.BASE.format(slug=slug)))
        jobs = []
        for item in data.get("jobs", []):
            title = item.get("title")
            url = item.get("absolute_url")
            if not title or not url:
                continue
            location = item.get("location", {}).get("name")
            posted_at = None
            if item.get("updated_at"):
                with contextlib.suppress(ValueError):
                    posted_at = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))  # noqa: FURB162 - fromisoformat("<date>Z") raises on 3.14 while the replaced form parses; behaviour is frozen
            raw_content = item.get("content", "") or ""
            description = re.sub(r"<[^>]+>", " ", raw_content).strip() if raw_content else None
            jobs.append(
                RawJob(
                    source="greenhouse",
                    company=slug,
                    title=title,
                    url=url,
                    location=location,
                    remote_type=normalize_remote_type(location),
                    posted_at=posted_at,
                    description=description,
                )
            )
        return jobs
