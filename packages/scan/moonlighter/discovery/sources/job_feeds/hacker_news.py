"""Hacker News' monthly 'Who is hiring?' thread, one job per top-level comment."""

import asyncio
import html
import re
from typing import Any, override

import httpx

from moonlighter.core.http_fetch import HEADERS, get_json
from moonlighter.discovery.sources.base import BaseScanner, RawJob, ScanStats, SourceStats
from moonlighter.discovery.sources.job_feeds.hacker_news_parsing import parse_title, parse_workplace


class HNWhoIsHiringScanner(BaseScanner):
    """Hacker News' monthly 'Who is hiring?' thread, via the official HN Firebase API.

    No auth, no bot-detection concern. Portal-wide like RemoteOKScanner -- not
    registered in SOURCES, dispatched separately in service.py, gated behind a
    config flag (off by default).

    The weakest signal of the 4 new boards: postings are free-text comments,
    not structured fields. Title/company extraction is best-effort (first
    line, split on '|' or '-'); when parsing fails, the comment's own HN
    permalink is still a reliable url, so a job is never dropped just
    because title/company parsing came back fuzzy -- only deleted/dead/
    empty comments are dropped.
    """

    BASE = "https://hacker-news.firebaseio.com/v0"
    _MAXIMUM_CONCURRENT_COMMENTS = 20
    _SUBMITTED_LOOKBACK = 10

    @override
    async def scan(
        self, company_slugs: list[str] | None = None, **keyword_arguments: Any
    ) -> list[RawJob]:
        stats: ScanStats | None = keyword_arguments.get("stats")
        async with httpx.AsyncClient(timeout=15) as client:
            jobs, errors = await self._fetch_thread_jobs(client)
        if stats is not None:
            stats["hn_whoishiring"] = SourceStats(companies=0, jobs=len(jobs), errors=errors)
        return jobs

    async def _fetch_thread_jobs(self, client: httpx.AsyncClient) -> tuple[list[RawJob], int]:
        thread_id = await self._find_latest_thread(client)
        if thread_id is None:
            return [], 1
        kids = await self._fetch_kids(client, thread_id)
        if not kids:
            return [], 1
        results = await self._fetch_comments(client, kids)
        jobs = [result for result in results if isinstance(result, RawJob)]
        # A None is a deleted/dead/empty comment -- not an error. Only
        # count entries that are neither a parsed job nor an expected
        # "nothing here" result.
        errors = sum(
            1 for result in results if not isinstance(result, RawJob) and result is not None
        )
        return jobs, errors

    async def _fetch_comments(
        self, client: httpx.AsyncClient, comment_ids: list[int]
    ) -> list[RawJob | BaseException | None]:
        semaphore = asyncio.Semaphore(self._MAXIMUM_CONCURRENT_COMMENTS)

        async def _fetch_one(comment_id: int) -> RawJob | None:
            async with semaphore:
                return await self._fetch_comment(client, comment_id)

        return await asyncio.gather(
            *(_fetch_one(comment_id) for comment_id in comment_ids), return_exceptions=True
        )

    async def _find_latest_thread(self, client: httpx.AsyncClient) -> int | None:
        submitted = await self._submitted_ids(client)
        for item_id in submitted[: self._SUBMITTED_LOOKBACK]:
            try:
                http_response = await client.get(
                    f"{self.BASE}/item/{item_id}.json", headers=HEADERS
                )
                if http_response.status_code != httpx.codes.OK:
                    continue
                item = http_response.json() or {}
            except Exception:  # noqa: BLE001, S112 - a submission that fails to load is skipped; the next one may be the thread
                continue
            if "who is hiring" in (item.get("title") or "").lower():
                return int(item_id)
        return None

    async def _submitted_ids(self, client: httpx.AsyncClient) -> Any:
        try:
            http_response = await client.get(f"{self.BASE}/user/whoishiring.json", headers=HEADERS)
            if http_response.status_code != httpx.codes.OK:
                return []
            return (http_response.json() or {}).get("submitted") or []
        except Exception:  # noqa: BLE001 - any failure to read the user record means no thread, which scan counts as one error
            return []

    async def _fetch_kids(self, client: httpx.AsyncClient, thread_id: int) -> list[int]:
        try:
            http_response = await client.get(f"{self.BASE}/item/{thread_id}.json", headers=HEADERS)
            if http_response.status_code != httpx.codes.OK:
                return []
            return list((http_response.json() or {}).get("kids") or [])
        except Exception:  # noqa: BLE001 - any failure to read the thread means no comments, which scan counts as one error
            return []

    async def _fetch_comment(self, client: httpx.AsyncClient, comment_id: int) -> RawJob | None:
        # A fetch failure must not flatten into the deleted/dead/empty None:
        # FetchError propagates to gather(return_exceptions=True) in scan(),
        # whose stats line counts exactly the not-RawJob-not-None entries.
        item = await get_json(client, f"{self.BASE}/item/{comment_id}.json") or {}
        if not item or item.get("deleted") or item.get("dead"):
            return None
        raw_text = item.get("text") or ""
        if not raw_text:
            return None
        text = re.sub(r"<[^>]+>", " ", html.unescape(raw_text)).strip()
        if not text:
            return None
        first_line = text.splitlines()[0]
        company, title = parse_title(first_line, text)
        remote_type, location = parse_workplace(text)
        return RawJob(
            source="hn_whoishiring",
            company=company,
            title=title,
            url=f"https://news.ycombinator.com/item?id={comment_id}",
            location=location,
            remote_type=remote_type,
            description=text,
        )
