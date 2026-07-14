"""Detects jobs that disappeared from their source (closed postings).

find_stale_jobs is a pure function relative to the database: it receives already-fetched
Job rows grouped by (source, company) and returns a verdict. It never writes to the DB and
never raises for a single company's failure — a transient error (network, malformed
response) is reported in failed_companies, never silently treated as "zero open jobs".
"""

from dataclasses import dataclass, field
from typing import Any

from gauntler.core import browser
from gauntler.core.db import Job
from gauntler.core.log import get_logger
from gauntler.discovery.sources.base import BaseScanner
from playwright.async_api import Error as PlaywrightError

logger = get_logger(__name__)

_LISTING_SOURCES = {"greenhouse", "lever", "ashby"}
_CLOSED_MARKERS = (
    "no longer accepting applications",
    "this job is no longer available",
)


@dataclass
class StalenessResult:
    stale: list[Job] = field(default_factory=list)
    failed_companies: list[str] = field(default_factory=list)


async def find_stale_jobs(
    jobs_by_company: dict[tuple[str, str], list[Job]],
    scanners: dict[str, BaseScanner],
    config: dict[str, Any],
) -> StalenessResult:
    result = StalenessResult()
    for (source, company), jobs in jobs_by_company.items():
        if source in _LISTING_SOURCES:
            await _check_via_listing(source, company, jobs, scanners, result)
        elif source == "linkedin":
            await _check_via_linkedin(company, jobs, config, result)
        else:
            result.failed_companies.append(f"{company} (source {source!r} has no listing check)")
    return result


async def _check_via_listing(
    source: str,
    company: str,
    jobs: list[Job],
    scanners: dict[str, BaseScanner],
    result: StalenessResult,
) -> None:
    scanner = scanners[source]
    try:
        raw = await scanner.scan([company])
    except Exception as e:
        logger.warning("staleness: %s scan failed for %s — %s", source, company, e)
        result.failed_companies.append(company)
        return
    if not isinstance(raw, list):
        logger.warning("staleness: %s scan returned unexpected type for %s", source, company)
        result.failed_companies.append(company)
        return
    open_urls = {r.url for r in raw}
    result.stale.extend(job for job in jobs if job.url not in open_urls)


async def _check_via_linkedin(
    company: str,
    jobs: list[Job],
    config: dict[str, Any],
    result: StalenessResult,
) -> None:
    try:
        page = await browser.new_page(config)
    except Exception as e:
        logger.warning("staleness: linkedin browser launch failed — %s", e)
        result.failed_companies.append(company)
        return
    try:
        for job in jobs:
            try:
                response = await page.goto(job.url, timeout=30000)
                status = response.status if response else None
                if status is not None and status >= 400:
                    result.stale.append(job)
                    continue
                content = (await page.content()).lower()
                if any(marker in content for marker in _CLOSED_MARKERS):
                    result.stale.append(job)
            except PlaywrightError as e:
                logger.warning("staleness: linkedin goto failed for %s — %s", job.url, e)
                if company not in result.failed_companies:
                    result.failed_companies.append(company)
    finally:
        await page.close()
