"""Recruitee job boards, on a recruitee.com subdomain or a custom career domain."""

import re
from typing import Any, override

import httpx

from moonlighter.core.http_fetch import get_json, require_dict
from moonlighter.discovery.sources.base import BaseScanner, RawJob, normalize_remote_type
from moonlighter.discovery.sources.company_boards.gathering import gather_jobs


class RecruiteeScanner(BaseScanner):
    @staticmethod
    def _offers_url(entry: str) -> str:
        """An entry with a dot is a custom career domain (jobs.channable.com).

        A bare slug is the recruitee.com subdomain. Most Recruitee customers
        use their own domain, and it serves the same offers API — verified
        live 2026-08-12.
        """
        if "." in entry:
            return f"https://{entry}/api/offers/"
        return f"https://{entry}.recruitee.com/api/offers/"

    @override
    async def scan(self, company_slugs: list[str], **keyword_arguments: Any) -> list[RawJob]:
        return await gather_jobs(
            "recruitee", company_slugs, self._fetch, stats=keyword_arguments.get("stats")
        )

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        data = require_dict(await get_json(client, self._offers_url(slug)))
        jobs = []
        for item in data.get("offers", []):
            title, url = item.get("title"), item.get("careers_apply_url")
            if not title or not url:
                continue
            location = item.get("location")
            remote_type = "remote" if item.get("remote") else normalize_remote_type(location)
            raw = item.get("description") or ""
            description = re.sub(r"<[^>]+>", " ", raw).strip() if raw else None
            jobs.append(
                RawJob(
                    source="recruitee",
                    company=slug,
                    title=title,
                    url=url,
                    location=location,
                    remote_type=remote_type,
                    description=description,
                )
            )
        return jobs
