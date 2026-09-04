import asyncio
import contextlib
import html
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, ClassVar

import httpx
from moonlighter.core.log import get_logger
from moonlighter.discovery.sources.base import (
    BaseScanner,
    RawJob,
    ScanStats,
    SourceStats,
    normalize_remote_type,
)

logger = get_logger(__name__)

HEADERS = {"User-Agent": "moonlighter/0.1"}

_Fetch = Callable[[httpx.AsyncClient, str], Awaitable[list[RawJob]]]


class FetchError(Exception):
    """A board fetch that failed: network error, non-200, non-JSON, wrong shape."""


async def _get_json(
    client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None
) -> Any:
    """GET + JSON-decode, raising FetchError on any failure instead of returning
    a shape the caller must remember to test. The raise is what keeps a dead API
    distinguishable from a company with no openings (the Ashby lesson)."""
    try:
        r = await client.get(url, headers=headers or HEADERS)
    except Exception as e:
        raise FetchError(f"{type(e).__name__}: {e}") from e
    if r.status_code != 200:
        raise FetchError(f"HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError as e:
        raise FetchError("non-JSON response") from e


def _require_dict(data: Any) -> dict[str, Any]:
    """The JSON payload's top-level shape, or FetchError — the one-line check
    six scanners repeated after _get_json (an API redesign, or an error page
    that decodes as a JSON string instead of the expected object, must not
    reach .get() and silently return nothing; it must be a visible scan
    error, the same reasoning _get_json's own docstring gives)."""
    if not isinstance(data, dict):
        raise FetchError("unexpected payload shape")
    return data


async def _gather_jobs(
    source: str, slugs: list[str], fetch: _Fetch, stats: ScanStats | None = None
) -> list[RawJob]:
    """Fetches all companies in parallel and flattens the result. A company that
    fails doesn't take down the others — but it is counted and logged, never
    silently dropped."""
    logger.info("[%s] scanning %d companies", source, len(slugs))
    jobs: list[RawJob] = []
    errors = 0
    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(
            *(fetch(client, slug) for slug in slugs), return_exceptions=True
        )
    for slug, result in zip(slugs, results, strict=True):
        if isinstance(result, list):
            jobs.extend(result)
        else:
            errors += 1
            logger.warning("[%s] fetch failed for %r: %s", source, slug, result)
    logger.info("[%s] %d raw jobs fetched (%d fetch errors)", source, len(jobs), errors)
    if stats is not None:
        stats[source] = SourceStats(companies=len(slugs), jobs=len(jobs), errors=errors)
    return jobs


class GreenhouseScanner(BaseScanner):
    BASE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs("greenhouse", company_slugs, self._fetch, kwargs.get("stats"))

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        data = _require_dict(await _get_json(client, self.BASE.format(slug=slug)))
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

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs("lever", company_slugs, self._fetch, kwargs.get("stats"))

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        raw_list = await _get_json(client, self.BASE.format(slug=slug))
        if not isinstance(raw_list, list):
            raise FetchError("unexpected payload shape")
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

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs("ashby", company_slugs, self._fetch, kwargs.get("stats"))

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        data = _require_dict(await _get_json(client, self.BASE.format(slug=slug)))
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
            location = item.get("location")
            remote_type = "remote" if item.get("isRemote") else normalize_remote_type(location)
            posted_at = None
            if item.get("publishedAt"):
                with contextlib.suppress(ValueError):
                    posted_at = datetime.fromisoformat(item["publishedAt"])
            jobs.append(
                RawJob(
                    source="ashby",
                    company=slug,
                    title=title,
                    url=url,
                    location=location,
                    remote_type=remote_type,
                    posted_at=posted_at,
                    description=item.get("descriptionPlain") or None,
                )
            )
        return jobs


class WorkableScanner(BaseScanner):
    BASE = "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs("workable", company_slugs, self._fetch, kwargs.get("stats"))

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        data = _require_dict(await _get_json(client, self.BASE.format(slug=slug)))
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


def _inhire_slug(title: str) -> str:
    """The URL slug InHire derives from displayName. Without it the SPA serves
    the shell (HTTP 200) but renders a black screen — verified live 2026-08-21.
    The one special case measured on a real posting: "|" becomes "or"
    ("Senior Elixir Engineer | Plataform" → senior-elixir-engineer-or-plataform);
    everything else is lowercase-ascii-hyphens."""
    text = title.replace("|", " or ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class InHireScanner(BaseScanner):
    """InHire (*.inhire.app) — big in the Brazilian market, no official public
    docs. The board is a React SPA, but InHire's own embed widget exposes the
    real endpoint: GET api.inhire.app/job-posts/public/pages with an X-Tenant
    header naming the company slug (the subdomain). Discovered by reading the
    shared tenant bundle for fetch() calls (2026-08-12), re-verified live
    2026-08-18: 16 postings for tenant "alice".

    A public per-job detail endpoint DOES exist — GET {BASE}/{jobId} with the
    same X-Tenant header, no auth (the old "403" note was stale; re-verified
    live 2026-08-24: HTTP 200, description 10.5k chars). One extra GET per
    listed posting fills the description that used to send every InHire job
    to needs_review.
    """

    BASE = "https://api.inhire.app/job-posts/public/pages"
    _REMOTE: ClassVar[dict[str, str]] = {
        "remote": "remote",
        "hybrid": "hybrid",
        "on-site": "onsite",
    }

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs("inhire", company_slugs, self._fetch, kwargs.get("stats"))

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        data = _require_dict(
            await _get_json(client, self.BASE, headers={**HEADERS, "X-Tenant": slug})
        )
        postings = data.get("jobsPage") or []
        if not isinstance(postings, list):
            raise FetchError("unexpected payload shape")
        published = [
            (str(item.get("displayName") or "").strip(), item)
            for item in postings
            if str(item.get("displayName") or "").strip()
            and item.get("jobId")
            and item.get("status") == "published"
        ]

        # Local import: posting.py imports this module (FetchError/_get_json),
        # so a top-level import here would be circular.
        from moonlighter.discovery.posting import _strip_tags

        async def _description(job_id: str) -> str | None:
            # A broken detail must not cost the posting: degrade to the old
            # behavior (None → needs_review), never drop the job.
            try:
                detail = await _get_json(
                    client, f"{self.BASE}/{job_id}", headers={**HEADERS, "X-Tenant": slug}
                )
            except FetchError:
                return None
            if not isinstance(detail, dict):
                return None
            return _strip_tags(str(detail.get("description") or ""))

        descriptions = await asyncio.gather(
            *(_description(str(item["jobId"])) for _, item in published)
        )
        jobs = []
        for (title, item), description in zip(published, descriptions, strict=True):
            job_id = item["jobId"]
            jobs.append(
                RawJob(
                    source="inhire",
                    company=slug,
                    title=title,
                    url=f"https://{slug}.inhire.app/vagas/{job_id}/{_inhire_slug(title)}",
                    location=item.get("location"),
                    remote_type=self._REMOTE.get(str(item.get("workplaceType") or "").lower()),
                    description=description,
                )
            )
        return jobs


class RecruiteeScanner(BaseScanner):
    @staticmethod
    def _offers_url(entry: str) -> str:
        """An entry with a dot is a custom career domain (jobs.channable.com);
        a bare slug is the recruitee.com subdomain. Most Recruitee customers
        use their own domain, and it serves the same offers API — verified
        live 2026-08-12."""
        if "." in entry:
            return f"https://{entry}/api/offers/"
        return f"https://{entry}.recruitee.com/api/offers/"

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs("recruitee", company_slugs, self._fetch, kwargs.get("stats"))

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        data = _require_dict(await _get_json(client, self._offers_url(slug)))
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

    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        return await _gather_jobs(
            "smartrecruiters", company_slugs, self._fetch, kwargs.get("stats")
        )

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
            data = _require_dict(
                await _get_json(client, self.LIST.format(slug=slug, offset=offset))
            )
            content = data.get("content") or []
            out.extend(content)
            total = data.get("totalFound", 0)
            offset += len(content)
            if offset >= total or not content:
                return out

    async def _detail(self, client: httpx.AsyncClient, slug: str, pid: str) -> str | None:
        await asyncio.sleep(0.1)
        try:
            data = await _get_json(client, self.DETAIL.format(slug=slug, pid=pid))
        except FetchError:
            return None
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

    async def scan(
        self, company_slugs: list[str] | None = None, *, keywords: str = "", **kwargs: Any
    ) -> list[RawJob]:
        stats: ScanStats | None = kwargs.get("stats")
        jobs: list[RawJob] = []
        offset = 0
        errors = 0
        async with httpx.AsyncClient(timeout=15) as client:
            while True:
                try:
                    data = await _get_json(
                        client, self.BASE.format(kw=keywords, limit=100, offset=offset)
                    )
                except FetchError as e:
                    logger.warning("[gupy] fetch failed: %s", e, exc_info=True)
                    errors += 1
                    break
                if not isinstance(data, dict):
                    errors += 1
                    break
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
                    break
        if stats is not None:
            stats["gupy"] = SourceStats(companies=0, jobs=len(jobs), errors=errors)
        return jobs


class RemoteOKScanner(BaseScanner):
    """RemoteOK is a portal-wide remote-jobs board (all companies, all
    categories) -- like GupyScanner, it doesn't route through
    _gather_jobs(slugs). Not registered in SOURCES; dispatched separately
    in service.py, gated behind a config flag (off by default)."""

    BASE = "https://remoteok.com/api"

    async def scan(self, company_slugs: list[str] | None = None, **kwargs: Any) -> list[RawJob]:
        stats: ScanStats | None = kwargs.get("stats")
        jobs: list[RawJob] = []
        errors = 0
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                data = await _get_json(client, self.BASE)
            except FetchError as e:
                logger.warning("[remoteok] fetch failed: %s", e, exc_info=True)
                errors, data = 1, []
        if not isinstance(data, list):
            # A shape change is an error, not a silent zero.
            errors, data = errors or 1, []
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
        if stats is not None:
            stats["remoteok"] = SourceStats(companies=0, jobs=len(jobs), errors=errors)
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

    async def scan(self, company_slugs: list[str] | None = None, **kwargs: Any) -> list[RawJob]:
        stats: ScanStats | None = kwargs.get("stats")
        jobs: list[RawJob] = []
        errors = 0
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                data = await _get_json(client, self.BASE)
            except FetchError as e:
                logger.warning("[remotive] fetch failed: %s", e, exc_info=True)
                errors, data = 1, {}
        if not isinstance(data, dict):
            # A shape change is an error, not a silent zero.
            errors, data = errors or 1, {}
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
        if stats is not None:
            stats["remotive"] = SourceStats(companies=0, jobs=len(jobs), errors=errors)
        return jobs


class WeWorkRemotelyScanner(BaseScanner):
    """WeWorkRemotely is a portal-wide RSS feed, like RemoteOKScanner -- not
    registered in SOURCES, dispatched separately in service.py, gated
    behind a config flag (off by default)."""

    BASE = "https://weworkremotely.com/categories/remote-programming-jobs.rss"

    async def scan(self, company_slugs: list[str] | None = None, **kwargs: Any) -> list[RawJob]:
        stats: ScanStats | None = kwargs.get("stats")
        jobs: list[RawJob] = []
        errors = 0
        body = ""
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                r = await client.get(self.BASE, headers=HEADERS)
            except Exception as e:
                logger.warning("[weworkremotely] fetch failed: %s", e, exc_info=True)
                errors = 1
            else:
                if r.status_code != 200:
                    logger.warning("[weworkremotely] fetch failed: HTTP %s", r.status_code)
                    errors = 1
                else:
                    body = r.text
        root = None
        if body:
            try:
                # S314: stdlib ElementTree parses untrusted network data (the RSS
                # feed is external, fetched over the network). Accepted: Python's
                # ElementTree does not resolve external entities/DTDs by default
                # (unlike some other XML parsers), so the residual risk is
                # entity-expansion DoS (e.g. "billion laughs"), not XXE file
                # disclosure -- a local nuisance (this call briefly hangs), not a
                # security breach, for a single-user local tool. No new
                # dependency (defusedxml) added for this; revisit if that
                # tradeoff changes.
                root = ET.fromstring(body)  # noqa: S314
            except ET.ParseError as e:
                logger.warning("[weworkremotely] malformed feed: %s", e, exc_info=True)
                errors = errors or 1
        if root is not None:
            for item in root.findall(".//item"):
                raw_title = (item.findtext("title") or "").strip()
                url = (item.findtext("link") or "").strip()
                if not raw_title or not url:
                    continue
                if ":" in raw_title:
                    company, _, position = raw_title.partition(":")
                    company = company.strip()
                    title = position.strip()
                else:
                    company = "WeWorkRemotely"
                    title = raw_title
                raw_desc = item.findtext("description") or ""
                # Same 3-pass normalization as RemotiveScanner (Task 2) -- a single
                # tag-strip regex leaves double spaces / space-before-punctuation on
                # nested tags. See that task's code comment for the concrete example.
                # None-init + if-guard (matching RemoteOKScanner/RemotiveScanner)
                # keeps mypy's inferred type as str | None throughout, not just str.
                description = None
                if raw_desc:
                    description = re.sub(r"<[^>]+>", " ", raw_desc).strip()
                    description = re.sub(r"\s+", " ", description)
                    description = re.sub(r"\s+([.!?,;:])", r"\1", description) or None
                location = (item.findtext("region") or "").strip() or None
                posted_at = None
                pub_date = item.findtext("pubDate")
                if pub_date:
                    with contextlib.suppress(Exception):
                        posted_at = parsedate_to_datetime(pub_date)
                jobs.append(
                    RawJob(
                        source="weworkremotely",
                        company=company,
                        title=title,
                        url=url,
                        location=location,
                        remote_type="remote",
                        description=description,
                        posted_at=posted_at,
                    )
                )
        if stats is not None:
            stats["weworkremotely"] = SourceStats(companies=0, jobs=len(jobs), errors=errors)
        return jobs


class HNWhoIsHiringScanner(BaseScanner):
    """Hacker News' monthly 'Who is hiring?' thread, via the official HN
    Firebase API (no auth, no bot-detection concern). Portal-wide like
    RemoteOKScanner -- not registered in SOURCES, dispatched separately in
    service.py, gated behind a config flag (off by default).

    The weakest signal of the 4 new boards: postings are free-text comments,
    not structured fields. Title/company extraction is best-effort (first
    line, split on '|' or '-'); when parsing fails, the comment's own HN
    permalink is still a reliable url, so a job is never dropped just
    because title/company parsing came back fuzzy -- only deleted/dead/
    empty comments are dropped."""

    BASE = "https://hacker-news.firebaseio.com/v0"
    _MAX_CONCURRENT_COMMENTS = 20
    _SUBMITTED_LOOKBACK = 10

    async def scan(self, company_slugs: list[str] | None = None, **kwargs: Any) -> list[RawJob]:
        stats: ScanStats | None = kwargs.get("stats")
        jobs: list[RawJob] = []
        errors = 0
        async with httpx.AsyncClient(timeout=15) as client:
            thread_id = await self._find_latest_thread(client)
            if thread_id is None:
                errors = 1
            else:
                kids = await self._fetch_kids(client, thread_id)
                if not kids:
                    errors = 1
                else:
                    sem = asyncio.Semaphore(self._MAX_CONCURRENT_COMMENTS)

                    async def _fetch_one(kid: int) -> RawJob | None:
                        async with sem:
                            return await self._fetch_comment(client, kid)

                    results = await asyncio.gather(
                        *(_fetch_one(kid) for kid in kids), return_exceptions=True
                    )
                    jobs = [r for r in results if isinstance(r, RawJob)]
                    # A None is a deleted/dead/empty comment -- not an error. Only
                    # count entries that are neither a parsed job nor an expected
                    # "nothing here" result.
                    errors = sum(1 for r in results if not isinstance(r, RawJob) and r is not None)
        if stats is not None:
            stats["hn_whoishiring"] = SourceStats(companies=0, jobs=len(jobs), errors=errors)
        return jobs

    async def _find_latest_thread(self, client: httpx.AsyncClient) -> int | None:
        try:
            r = await client.get(f"{self.BASE}/user/whoishiring.json", headers=HEADERS)
            if r.status_code != 200:
                return None
            submitted = (r.json() or {}).get("submitted") or []
        except Exception:
            return None
        for item_id in submitted[: self._SUBMITTED_LOOKBACK]:
            try:
                r = await client.get(f"{self.BASE}/item/{item_id}.json", headers=HEADERS)
                if r.status_code != 200:
                    continue
                item = r.json() or {}
            except Exception:  # noqa: S112
                continue
            if "who is hiring" in (item.get("title") or "").lower():
                return int(item_id)
        return None

    async def _fetch_kids(self, client: httpx.AsyncClient, thread_id: int) -> list[int]:
        try:
            r = await client.get(f"{self.BASE}/item/{thread_id}.json", headers=HEADERS)
            if r.status_code != 200:
                return []
            return list((r.json() or {}).get("kids") or [])
        except Exception:
            return []

    async def _fetch_comment(self, client: httpx.AsyncClient, kid: int) -> RawJob | None:
        # A fetch failure must not flatten into the deleted/dead/empty None:
        # FetchError propagates to gather(return_exceptions=True) in scan(),
        # whose stats line counts exactly the not-RawJob-not-None entries.
        item = await _get_json(client, f"{self.BASE}/item/{kid}.json") or {}
        if not item or item.get("deleted") or item.get("dead"):
            return None
        raw_text = item.get("text") or ""
        if not raw_text:
            return None
        text = re.sub(r"<[^>]+>", " ", html.unescape(raw_text)).strip()
        if not text:
            return None
        first_line = text.splitlines()[0]
        company, title = self._parse_title(first_line, text)
        return RawJob(
            source="hn_whoishiring",
            company=company,
            title=title,
            url=f"https://news.ycombinator.com/item?id={kid}",
            location=None,
            remote_type=None,
            description=text,
        )

    _MAX_TITLE_LEN = 80

    @classmethod
    def _cap(cls, text: str) -> str:
        return (text[: cls._MAX_TITLE_LEN] + "…") if len(text) > cls._MAX_TITLE_LEN else text

    @classmethod
    def _parse_title(cls, first_line: str, full_text: str) -> tuple[str, str]:
        # HN comments render paragraphs as <p>, which the tag-strip in
        # _fetch_comment turns into a space, not a newline -- so "first_line"
        # is really "the whole flattened comment" and `rest` after the first
        # separator is unbounded (a real ~1200-char title was observed live).
        # Cap it the same way as the no-separator fallback below.
        for sep in ("|", "-"):
            if sep in first_line:
                company, _, rest = first_line.partition(sep)
                company = company.strip()
                if company:
                    return company, cls._cap(rest.strip() or first_line.strip())
        return "HN Who's Hiring", cls._cap(full_text) or "Untitled posting"
