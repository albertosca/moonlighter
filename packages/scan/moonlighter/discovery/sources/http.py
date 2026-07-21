import asyncio
import contextlib
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from moonlighter.core.log import get_logger
from moonlighter.discovery.sources.base import BaseScanner, RawJob, normalize_remote_type

logger = get_logger(__name__)

_Fetch = Callable[[httpx.AsyncClient, str], Awaitable[list[RawJob]]]


async def _gather_jobs(source: str, slugs: list[str], fetch: _Fetch) -> list[RawJob]:
    """Fetches all companies in parallel and flattens the result. A company that
    fails (exception in fetch) is ignored, it doesn't take down the others."""
    logger.info("[%s] scanning %d companies", source, len(slugs))
    jobs: list[RawJob] = []
    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(
            *(fetch(client, slug) for slug in slugs), return_exceptions=True
        )
    for result in results:
        if isinstance(result, list):
            jobs.extend(result)
    logger.info("[%s] %d raw jobs fetched", source, len(jobs))
    return jobs


class GreenhouseScanner(BaseScanner):
    BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    HEADERS: ClassVar[dict[str, str]] = {"User-Agent": "moonlighter/0.1"}

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs("greenhouse", company_slugs, self._fetch)

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
    HEADERS: ClassVar[dict[str, str]] = {"User-Agent": "moonlighter/0.1"}

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs("lever", company_slugs, self._fetch)

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
        "User-Agent": "moonlighter/0.1",
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

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs("ashby", company_slugs, self._fetch)

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


class WorkableScanner(BaseScanner):
    BASE = "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"
    HEADERS: ClassVar[dict[str, str]] = {"User-Agent": "moonlighter/0.1"}

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs("workable", company_slugs, self._fetch)

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        try:
            r = await client.get(self.BASE.format(slug=slug), headers=self.HEADERS)
        except Exception:
            return []
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, dict):
            return []
        jobs = []
        for item in data.get("jobs", []):
            title, url = item.get("title"), item.get("application_url")
            if not title or not url:
                continue
            location = (
                ", ".join(
                    p for p in (item.get("city"), item.get("state"), item.get("country")) if p
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


class RecruiteeScanner(BaseScanner):
    BASE = "https://{slug}.recruitee.com/api/offers/"
    HEADERS: ClassVar[dict[str, str]] = {"User-Agent": "moonlighter/0.1"}

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs("recruitee", company_slugs, self._fetch)

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        try:
            r = await client.get(self.BASE.format(slug=slug), headers=self.HEADERS)
        except Exception:
            return []
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, dict):
            return []
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


class SmartRecruitersScanner(BaseScanner):
    LIST = "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}"
    DETAIL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings/{pid}"
    APPLY = "https://jobs.smartrecruiters.com/{slug}/{pid}"
    HEADERS: ClassVar[dict[str, str]] = {"User-Agent": "moonlighter/0.1"}

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs("smartrecruiters", company_slugs, self._fetch)

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        postings = await self._list(client, slug)
        jobs = []
        for p in postings:
            pid, title = p.get("id"), p.get("name")
            if not pid or not title:
                continue
            loc = p.get("location") or {}
            location = ", ".join(x for x in (loc.get("city"), loc.get("country")) if x) or None
            remote_type = (
                "remote"
                if loc.get("remote")
                else "hybrid"
                if loc.get("hybrid")
                else normalize_remote_type(location)
            )
            description = await self._detail(client, slug, pid)
            jobs.append(
                RawJob(
                    source="smartrecruiters",
                    company=slug,
                    title=title,
                    url=self.APPLY.format(slug=slug, pid=pid),
                    location=location,
                    remote_type=remote_type,
                    description=description,
                )
            )
        return jobs

    async def _list(self, client: httpx.AsyncClient, slug: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        offset = 0
        while True:
            try:
                r = await client.get(
                    self.LIST.format(slug=slug, offset=offset), headers=self.HEADERS
                )
            except Exception:
                return out
            if r.status_code != 200:
                return out
            data = r.json()
            if not isinstance(data, dict):
                return out
            content = data.get("content") or []
            out.extend(content)
            total = data.get("totalFound", 0)
            offset += len(content)
            if offset >= total or not content:
                return out

    async def _detail(self, client: httpx.AsyncClient, slug: str, pid: str) -> str | None:
        await asyncio.sleep(0.1)
        try:
            r = await client.get(self.DETAIL.format(slug=slug, pid=pid), headers=self.HEADERS)
        except Exception:
            return None
        if r.status_code != 200:
            return None
        data = r.json()
        if not isinstance(data, dict):
            return None
        sections = (data.get("jobAd") or {}).get("sections") or {}
        parts = [s.get("text", "") for s in sections.values() if isinstance(s, dict)]
        raw = " ".join(p for p in parts if p)
        return re.sub(r"<[^>]+>", " ", raw).strip() or None if raw else None


class GupyScanner(BaseScanner):
    """Gupy is a portal-wide keyword feed (one global search across all companies
    hosted on Gupy), not a per-company board -- so unlike the other HTTP scanners
    it is keyword-driven and builds its own client rather than routing through
    _gather_jobs(slugs). Not registered in SOURCES; dispatched separately (mirrors
    the LinkedIn model) and gated behind a config flag in service.py."""

    BASE = "https://employability-portal.gupy.io/api/v1/jobs?jobName={kw}&limit={limit}&offset={offset}"
    HEADERS: ClassVar[dict[str, str]] = {"User-Agent": "moonlighter/0.1"}

    async def scan(
        self, company_slugs: list[str] | None = None, *, keywords: str = "", **kwargs: Any
    ) -> list[RawJob]:
        jobs: list[RawJob] = []
        offset = 0
        async with httpx.AsyncClient(timeout=15) as client:
            while True:
                try:
                    r = await client.get(
                        self.BASE.format(kw=keywords, limit=100, offset=offset),
                        headers=self.HEADERS,
                    )
                except Exception:
                    return jobs
                if r.status_code != 200:
                    return jobs
                data = r.json()
                if not isinstance(data, dict):
                    return jobs
                page = data.get("data") or []
                for item in page:
                    title, url = item.get("name"), item.get("jobUrl")
                    if not title or not url:
                        continue
                    location = (
                        ", ".join(
                            x
                            for x in (item.get("city"), item.get("state"), item.get("country"))
                            if x
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
                    jobs.append(
                        RawJob(
                            source="gupy",
                            company=item.get("careerPageName") or "gupy",
                            title=title,
                            url=url,
                            location=location,
                            remote_type=remote_type,
                            description=description,
                        )
                    )
                # Advance by the actual page length (never by the server-reported
                # `limit`, which can legitimately be 0 and spin the loop forever --
                # the same bug just fixed for SmartRecruiters).
                offset += len(page)
                total = (data.get("pagination") or {}).get("total", 0)
                if not page or offset >= total:
                    return jobs


class RemoteOKScanner(BaseScanner):
    """RemoteOK is a portal-wide remote-jobs board (all companies, all
    categories) -- like GupyScanner, it doesn't route through
    _gather_jobs(slugs). Not registered in SOURCES; dispatched separately
    in service.py, gated behind a config flag (off by default)."""

    BASE = "https://remoteok.com/api"
    HEADERS: ClassVar[dict[str, str]] = {"User-Agent": "moonlighter/0.1"}

    async def scan(self, company_slugs: list[str] | None = None, **kwargs: Any) -> list[RawJob]:
        jobs: list[RawJob] = []
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                r = await client.get(self.BASE, headers=self.HEADERS)
            except Exception:
                return jobs
            if r.status_code != 200:
                return jobs
            data = r.json()
        if not isinstance(data, list):
            return jobs
        for item in data:
            title, url = item.get("position"), item.get("url")
            if not title or not url:
                continue
            raw_desc = item.get("description") or ""
            description = None
            if raw_desc:
                description = re.sub(r"<[^>]+>", " ", raw_desc).strip()
                description = re.sub(r"\s+", " ", description)
                description = re.sub(r"\s+([.!?,;:])", r"\1", description) or None
            jobs.append(
                RawJob(
                    source="remoteok",
                    company=item.get("company") or "RemoteOK",
                    title=title,
                    url=url,
                    location=item.get("location") or None,
                    remote_type="remote",
                    description=description,
                )
            )
        return jobs


class RemotiveScanner(BaseScanner):
    """Remotive is a portal-wide remote-jobs board like RemoteOKScanner --
    not registered in SOURCES, dispatched separately in service.py, gated
    behind a config flag (off by default).

    ToS note: max 4 requests/day, must link back to Remotive as source. No
    rate-limiter here (no precedent for one in this codebase) -- the config
    flag is the control point; whoever enables this scanner is responsible
    for not scanning more than a few times a day."""

    BASE = "https://remotive.com/api/remote-jobs?category=software-dev"
    HEADERS: ClassVar[dict[str, str]] = {"User-Agent": "moonlighter/0.1"}

    async def scan(self, company_slugs: list[str] | None = None, **kwargs: Any) -> list[RawJob]:
        jobs: list[RawJob] = []
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                r = await client.get(self.BASE, headers=self.HEADERS)
            except Exception:
                return jobs
            if r.status_code != 200:
                return jobs
            data = r.json()
        if not isinstance(data, dict):
            return jobs
        for item in data.get("jobs") or []:
            title, url = item.get("title"), item.get("url")
            if not title or not url:
                continue
            raw_desc = item.get("description") or ""
            description = None
            if raw_desc:
                description = re.sub(r"<[^>]+>", " ", raw_desc).strip()
                description = re.sub(r"\s+", " ", description)
                description = re.sub(r"\s+([.!?,;:])", r"\1", description) or None
            jobs.append(
                RawJob(
                    source="remotive",
                    company=item.get("company_name") or "Remotive",
                    title=title,
                    url=url,
                    location=item.get("candidate_required_location") or None,
                    remote_type="remote",
                    description=description,
                )
            )
        return jobs
