"""Ashby job boards, read through the public REST posting API."""

import contextlib
from datetime import datetime
from typing import Any, override

import httpx

from moonlighter.core.http_fetch import FetchError, get_json, require_dict
from moonlighter.discovery.sources.base import (
    BaseScanner,
    RawJob,
    join_locations,
    normalize_remote_type,
    remote_type_from_workplace,
)
from moonlighter.discovery.sources.company_boards.gathering import gather_jobs


class AshbyScanner(BaseScanner):
    """Ashby public job board API.

    Uses the REST posting API. The previous implementation posted a `jobPostings`
    GraphQL query to jobs.ashbyhq.com/api/non-user-graphql; Ashby retired that
    field, and the endpoint now answers HTTP 200 with an `errors` payload — which
    this scanner turned into an empty list. Every Ashby company therefore reported
    zero openings, silently, and indistinguishably from a company that is simply
    not hiring. Probed 2026-08-03 across 39 slugs (linear, posthog, supabase, …):
    0 jobs through GraphQL, 2546 through the endpoint below.
    """

    BASE = "https://api.ashbyhq.com/posting-api/job-board/{slug}"

    @override
    async def scan(self, company_slugs: list[str], **keyword_arguments: Any) -> list[RawJob]:
        return await gather_jobs(
            "ashby", company_slugs, self._fetch, stats=keyword_arguments.get("stats")
        )

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        data = require_dict(await get_json(client, self.BASE.format(slug=slug)))
        postings = data.get("jobs") or []
        if not isinstance(postings, list):
            raise FetchError("unexpected payload shape")
        jobs = []
        for item in postings:
            title = item.get("title")
            url = item.get("jobUrl")
            # isListed=False is a posting the company has unpublished: the page is
            # still reachable but is not accepting applications.
            if not title or not url or item.get("isListed") is False:
                continue
            location = self._location(item)
            jobs.append(
                RawJob(
                    source="ashby",
                    company=slug,
                    title=title,
                    url=url,
                    location=location,
                    remote_type=self._remote_type(item, location),
                    posted_at=self._published_at(item),
                    description=item.get("descriptionPlain") or None,
                )
            )
        return jobs

    @staticmethod
    def _location(item: dict[str, Any]) -> str | None:
        secondary = item.get("secondaryLocations")
        return join_locations(
            item.get("location"),
            [place.get("location") for place in secondary if isinstance(place, dict)]
            if isinstance(secondary, list)
            else None,
        )

    @staticmethod
    def _remote_type(item: dict[str, Any], location: str | None) -> str | None:
        return (
            "remote"
            if item.get("isRemote")
            else normalize_remote_type(location)
            or remote_type_from_workplace(item.get("workplaceType"))
        )

    @staticmethod
    def _published_at(item: dict[str, Any]) -> datetime | None:
        posted_at = None
        if item.get("publishedAt"):
            with contextlib.suppress(ValueError):
                posted_at = datetime.fromisoformat(item["publishedAt"])
        return posted_at
