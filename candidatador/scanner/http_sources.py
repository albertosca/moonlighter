import asyncio
import re
from datetime import datetime, timezone
from typing import Optional
import httpx
from candidatador.scanner.base import BaseScanner, RawJob, normalize_remote_type

class GreenhouseScanner(BaseScanner):
    BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    HEADERS = {"User-Agent": "candidatador/0.1"}

    async def scan(self, company_slugs: list[str], **kwargs) -> list[RawJob]:
        jobs = []
        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [self._fetch(client, slug) for slug in company_slugs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                jobs.extend(result)
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
        jobs = []
        for item in data.get("jobs", []):
            location = item.get("location", {}).get("name")
            posted_at = None
            if item.get("updated_at"):
                try:
                    posted_at = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
                except ValueError:
                    pass
            raw_content = item.get("content", "") or ""
            description = re.sub(r'<[^>]+>', ' ', raw_content).strip() if raw_content else None
            jobs.append(RawJob(
                source="greenhouse",
                company=slug,
                title=item["title"],
                url=item["absolute_url"],
                location=location,
                remote_type=normalize_remote_type(location),
                posted_at=posted_at,
                description=description,
            ))
        return jobs


class LeverScanner(BaseScanner):
    BASE = "https://api.lever.co/v0/postings/{slug}"
    HEADERS = {"User-Agent": "candidatador/0.1"}

    async def scan(self, company_slugs: list[str], **kwargs) -> list[RawJob]:
        jobs = []
        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [self._fetch(client, slug) for slug in company_slugs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                jobs.extend(result)
        return jobs

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        url = self.BASE.format(slug=slug)
        try:
            r = await client.get(url, headers=self.HEADERS)
        except Exception:
            return []
        if r.status_code != 200:
            return []
        jobs = []
        for item in r.json():
            title = item.get("text", "")
            url = item.get("hostedUrl", "")
            if not title or not url:
                continue
            location = item.get("categories", {}).get("location")
            posted_at = None
            if item.get("createdAt"):
                posted_at = datetime.fromtimestamp(item["createdAt"] / 1000, tz=timezone.utc)
            jobs.append(RawJob(
                source="lever",
                company=slug,
                title=title,
                url=url,
                location=location,
                remote_type=normalize_remote_type(location),
                posted_at=posted_at,
            ))
        return jobs


class AshbyScanner(BaseScanner):
    """Ashby public job board API."""
    BASE = "https://jobs.ashbyhq.com/api/non-user-graphql"
    HEADERS = {"User-Agent": "candidatador/0.1", "Content-Type": "application/json"}
    QUERY = """
    query jobPostings($organizationHostedJobsPageName: String!) {
      jobPostings(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
        id title locationName isRemote publishedDate
        jobPostingAbsoluteUrl
      }
    }
    """

    async def scan(self, company_slugs: list[str], **kwargs) -> list[RawJob]:
        jobs = []
        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [self._fetch(client, slug) for slug in company_slugs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                jobs.extend(result)
        return jobs

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        try:
            r = await client.post(self.BASE, headers=self.HEADERS, json={
                "operationName": "jobPostings",
                "query": self.QUERY,
                "variables": {"organizationHostedJobsPageName": slug},
            })
        except Exception:
            return []
        if r.status_code != 200:
            return []
        data = r.json().get("data", {}).get("jobPostings", [])
        jobs = []
        for item in data:
            remote_type = "remote" if item.get("isRemote") else normalize_remote_type(item.get("locationName"))
            posted_at = None
            if item.get("publishedDate"):
                try:
                    posted_at = datetime.fromisoformat(item["publishedDate"])
                except ValueError:
                    pass
            jobs.append(RawJob(
                source="ashby",
                company=slug,
                title=item.get("title", ""),
                url=item.get("jobPostingAbsoluteUrl", ""),
                location=item.get("locationName"),
                remote_type=remote_type,
                posted_at=posted_at,
            ))
        return jobs
