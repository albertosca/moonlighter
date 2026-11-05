"""InHire job boards, read through the endpoint InHire's own embed widget calls."""

import asyncio
import re
import unicodedata
from typing import Any, ClassVar, override

import httpx

from moonlighter.core.http_fetch import HEADERS, FetchError, get_json, require_dict
from moonlighter.core.posting import strip_tags
from moonlighter.discovery.sources.base import BaseScanner, RawJob
from moonlighter.discovery.sources.company_boards.gathering import gather_jobs


def _inhire_slug(title: str) -> str:
    """The URL slug InHire derives from displayName.

    Without it the SPA serves the shell (HTTP 200) but renders a black screen —
    verified live 2026-08-21. The one special case measured on a real posting:
    "|" becomes "or" ("Senior Elixir Engineer | Plataform" →
    senior-elixir-engineer-or-plataform); everything else is
    lowercase-ascii-hyphens.
    """
    text = title.replace("|", " or ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class InHireScanner(BaseScanner):
    """InHire (*.inhire.app) — big in the Brazilian market, no official public docs.

    The board is a React SPA, but InHire's own embed widget exposes the
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

    @override
    async def scan(self, company_slugs: list[str], **keyword_arguments: Any) -> list[RawJob]:
        return await gather_jobs(
            "inhire", company_slugs, self._fetch, stats=keyword_arguments.get("stats")
        )

    async def _fetch(self, client: httpx.AsyncClient, slug: str) -> list[RawJob]:
        data = require_dict(
            await get_json(client, self.BASE, headers={**HEADERS, "X-Tenant": slug})
        )
        postings = data.get("jobsPage") or []
        if not isinstance(postings, list):
            raise FetchError("unexpected payload shape")
        published = self._published(postings)
        descriptions = await asyncio.gather(
            *(self._description(client, slug, str(item["jobId"])) for _, item in published)
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

    @staticmethod
    def _published(postings: list[Any]) -> list[tuple[str, dict[str, Any]]]:
        return [
            (str(item.get("displayName") or "").strip(), item)
            for item in postings
            if str(item.get("displayName") or "").strip()
            and item.get("jobId")
            and item.get("status") == "published"
        ]

    async def _description(self, client: httpx.AsyncClient, slug: str, job_id: str) -> str | None:
        # A broken detail must not cost the posting: degrade to the old
        # behavior (None → needs_review), never drop the job.
        try:
            detail = await get_json(
                client, f"{self.BASE}/{job_id}", headers={**HEADERS, "X-Tenant": slug}
            )
        except FetchError:
            return None
        if not isinstance(detail, dict):
            return None
        return strip_tags(str(detail.get("description") or ""))
