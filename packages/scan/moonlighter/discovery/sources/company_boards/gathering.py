"""The parallel fetch every company-board scanner shares: one client, all slugs, failures counted."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx

from moonlighter.core.log import get_logger
from moonlighter.discovery.sources.base import RawJob, ScanStats, SourceStats

logger = get_logger(__name__)

_Fetch = Callable[[httpx.AsyncClient, str], Awaitable[list[RawJob]]]


async def gather_jobs(
    source: str, slugs: list[str], fetch: _Fetch, *, stats: ScanStats | None = None
) -> list[RawJob]:
    """Fetches all companies in parallel and flattens the result.

    A company that fails doesn't take down the others — but it is counted and
    logged, never silently dropped.
    """
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
