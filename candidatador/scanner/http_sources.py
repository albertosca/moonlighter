import asyncio
import contextlib
import re
from datetime import UTC, datetime
from typing import ClassVar

import httpx

from candidatador.log import get_logger
from candidatador.scanner.base import BaseScanner, RawJob, normalize_remote_type

logger = get_logger(__name__)


class GreenhouseScanner(BaseScanner):
    BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    HEADERS: ClassVar[dict[str, str]] = {"User-Agent": "candidatador/0.1"}

    async def scan(self, company_slugs: list[str], **kwargs) -> list[RawJob]:
        logger.info("[greenhouse] scanning %d companies", len(company_slugs))
        jobs = []
        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [self._fetch(client, slug) for slug in company_slugs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                jobs.extend(result)
        logger.info("[greenhouse] %d raw jobs fetched", len(jobs))
        return jobs

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        url = self.BASE.format(slug=slug)
        try:
            r = await client.get(url, headers=self.HEADERS)
        except Exception:
            return []
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, dict):
            return []
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
                    posted_at = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
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


class LeverScanner(BaseScanner):
    BASE = "https://api.lever.co/v0/postings/{slug}"
    HEADERS: ClassVar[dict[str, str]] = {"User-Agent": "candidatador/0.1"}

    async def scan(self, company_slugs: list[str], **kwargs) -> list[RawJob]:
        logger.info("[lever] scanning %d companies", len(company_slugs))
        jobs = []
        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [self._fetch(client, slug) for slug in company_slugs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                jobs.extend(result)
        logger.info("[lever] %d raw jobs fetched", len(jobs))
        return jobs

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        url = self.BASE.format(slug=slug)
        try:
            r = await client.get(url, headers=self.HEADERS)
        except Exception:
            return []
        if r.status_code != 200:
            return []
        raw_list = r.json()
        if not isinstance(raw_list, list):
            return []
        jobs = []
        for item in raw_list:
            title = item.get("text", "")
            url = item.get("hostedUrl", "")
            if not title or not url:
                continue
            location = item.get("categories", {}).get("location")
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
                    remote_type=normalize_remote_type(location),
                    posted_at=posted_at,
                    description=item.get("descriptionPlain") or None,
                )
            )
        return jobs


class AshbyScanner(BaseScanner):
    """Ashby public job board API."""

    BASE = "https://jobs.ashbyhq.com/api/non-user-graphql"
    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": "candidatador/0.1",
        "Content-Type": "application/json",
    }
    QUERY = """
    query jobPostings($organizationHostedJobsPageName: String!) {
      jobPostings(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
        id title locationName isRemote publishedDate
        jobPostingAbsoluteUrl descriptionPlain
      }
    }
    """

    async def scan(self, company_slugs: list[str], **kwargs) -> list[RawJob]:
        logger.info("[ashby] scanning %d companies", len(company_slugs))
        jobs = []
        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [self._fetch(client, slug) for slug in company_slugs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                jobs.extend(result)
        logger.info("[ashby] %d raw jobs fetched", len(jobs))
        return jobs

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        try:
            r = await client.post(
                self.BASE,
                headers=self.HEADERS,
                json={
                    "operationName": "jobPostings",
                    "query": self.QUERY,
                    "variables": {"organizationHostedJobsPageName": slug},
                },
            )
        except Exception:
            return []
        if r.status_code != 200:
            return []
        response_data = r.json()
        if "errors" in response_data:
            return []
        job_postings = response_data.get("data", {}).get("jobPostings") or []
        if not isinstance(job_postings, list):
            return []
        jobs = []
        for item in job_postings:
            title = item.get("title")
            url = item.get("jobPostingAbsoluteUrl")
            if not title or not url:
                continue
            remote_type = (
                "remote"
                if item.get("isRemote")
                else normalize_remote_type(item.get("locationName"))
            )
            posted_at = None
            if item.get("publishedDate"):
                with contextlib.suppress(ValueError):
                    posted_at = datetime.fromisoformat(item["publishedDate"])
            jobs.append(
                RawJob(
                    source="ashby",
                    company=slug,
                    title=title,
                    url=url,
                    location=item.get("locationName"),
                    remote_type=remote_type,
                    posted_at=posted_at,
                    description=item.get("descriptionPlain") or None,
                )
            )
        return jobs
