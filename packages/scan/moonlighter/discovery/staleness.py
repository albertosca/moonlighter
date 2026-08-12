"""Detects jobs that disappeared from their source (closed postings).

find_stale_jobs is a pure function relative to the database: it receives already-fetched
Job rows grouped by (source, company) and returns a verdict. It never writes to the DB and
never raises for a single company's failure — a transient error (network, malformed
response) is reported in failed_companies, never silently treated as "zero open jobs".
"""

from dataclasses import dataclass, field
from typing import Any

from moonlighter.core.db import Job
from moonlighter.core.log import get_logger
from moonlighter.core.plugins import discover_entry_points_by_name
from moonlighter.discovery.sources.base import BaseScanner
from moonlighter.discovery.sources.registry import LISTING_SOURCES as _LISTING_SOURCES
from moonlighter.discovery.sources.registry import PORTAL_SOURCES
from moonlighter.discovery.urls import normalize_job_url

logger = get_logger(__name__)


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
    # A browser-based staleness checker for a non-listing source (e.g. LinkedIn) is
    # optionally provided by a private plugin package -- see
    # docs/superpowers/specs/2026-07-22-linkedin-plugin-split-design.md. Never
    # hardcoded here: a source with no registered listing check AND no registered
    # checker plugin falls through to the "has no listing check" branch below.
    checkers = discover_entry_points_by_name("moonlighter.staleness_checkers")
    portal_counts: dict[str, int] = {}
    for (source, company), jobs in jobs_by_company.items():
        if source in _LISTING_SOURCES:
            await _check_via_listing(source, company, jobs, scanners, result)
        elif source in PORTAL_SOURCES:
            portal_counts[source] = portal_counts.get(source, 0) + len(jobs)
        elif source in checkers:
            # Plugin-provided (untrusted, unlike the first-party listing check above) --
            # guard the call so one misbehaving checker can't abort the whole run.
            try:
                await checkers[source](company, jobs, config, result)
            except Exception as e:
                logger.warning("staleness: %s checker failed for %s — %s", source, company, e)
                if company not in result.failed_companies:
                    result.failed_companies.append(company)
        else:
            result.failed_companies.append(f"{company} (source {source!r} has no listing check)")
    for source, count in sorted(portal_counts.items()):
        result.failed_companies.append(
            f"{count} {source} job(s) (portal feed, no per-company listing)"
        )
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
    # Stored job.url is normalized (Task 5 strips the Recruitee /c/new apply
    # suffix), but the fresh listing's raw URLs are not — normalize both sides,
    # or every freshly-stored Recruitee job compares unequal and is archived
    # as stale on its very first re-scan.
    open_urls = {normalize_job_url(r.url) for r in raw}
    result.stale.extend(job for job in jobs if normalize_job_url(job.url) not in open_urls)
