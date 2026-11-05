"""Lever job boards, read through the public postings API."""

from datetime import UTC, datetime
from typing import Any, override

import httpx

from moonlighter.core.http_fetch import FetchError, get_json
from moonlighter.discovery.sources.base import (
    BaseScanner,
    RawJob,
    join_locations,
    normalize_remote_type,
    remote_type_from_workplace,
)
from moonlighter.discovery.sources.company_boards.gathering import gather_jobs


class LeverScanner(BaseScanner):
    BASE = "https://api.lever.co/v0/postings/{slug}"

    @override
    async def scan(self, company_slugs: list[str], **keyword_arguments: Any) -> list[RawJob]:
        return await gather_jobs(
            "lever", company_slugs, self._fetch, stats=keyword_arguments.get("stats")
        )

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        raw_list = await get_json(client, self.BASE.format(slug=slug))
        if not isinstance(raw_list, list):
            raise FetchError("unexpected payload shape")
        jobs = []
        for item in raw_list:
            title = item.get("text", "")
            url = item.get("hostedUrl", "")
            if not title or not url:
                continue
            categories = item.get("categories", {})
            location = join_locations(categories.get("location"), categories.get("allLocations"))
            posted_at = None
            if item.get("createdAt"):
                posted_at = datetime.fromtimestamp(item["createdAt"] / 1000, tz=UTC)
            jobs.append(
                RawJob(
                    source="lever",
                    company=slug,
                    title=title,
                    url=url,
                    location=location,
                    # The API's workplaceType only fills what the text leaves open.
                    remote_type=normalize_remote_type(location)
                    or remote_type_from_workplace(item.get("workplaceType")),
                    posted_at=posted_at,
                    description=item.get("descriptionPlain") or None,
                )
            )
        return jobs
