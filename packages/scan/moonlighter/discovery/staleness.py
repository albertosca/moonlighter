"""Detects jobs that disappeared from their source (closed postings).

find_stale_jobs is a pure function relative to the database: it receives already-fetched
Job rows grouped by (source, company) and returns a verdict. It never writes to the DB and
never raises for a single company's failure — a transient error (network, malformed
response) is reported in failed_companies, never silently treated as "zero open jobs".
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from moonlighter.core.db import Job
from moonlighter.core.log import get_logger
from moonlighter.core.plugins import discover_entry_points_by_name
from moonlighter.core.web.urls import normalize_job_url
from moonlighter.discovery.sources.base import BaseScanner, ScanStats
from moonlighter.discovery.sources.registry import LISTING_SOURCES, PORTAL_SOURCES

logger = get_logger(__name__)


@dataclass
class StalenessResult:
    stale: list[Job] = field(default_factory=list)
    # Portal jobs past portal_max_age_days: age is the only closing signal a
    # portal feed offers, so these archive as aged-out, never as closed-at-source.
    stale_by_age: list[Job] = field(default_factory=list)
    # Jobs from a source with no listing to diff against (source='manual', or a
    # source with no checker plugin): only a person opening the link can say
    # whether it closed, so they are reported one by one, never archived.
    unverifiable: list[Job] = field(default_factory=list)
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
    # checker plugin lands in result.unverifiable, for a person to confirm by hand.
    checkers = discover_entry_points_by_name("moonlighter.staleness_checkers")
    portal_counts: dict[str, int] = {}
    for (source, company), jobs in jobs_by_company.items():
        if source in LISTING_SOURCES:
            await _check_via_listing(source, company, jobs, scanners=scanners, result=result)
        elif source in PORTAL_SOURCES:
            _tally_portal_jobs(
                source, jobs, config=config, result=result, portal_counts=portal_counts
            )
        elif source in checkers:
            check = partial(checkers[source], company, jobs, config, result)
            await _run_plugin_checker(check, source, company, result=result)
        else:
            result.unverifiable.extend(jobs)
    result.failed_companies.extend(_portal_notes(portal_counts))
    return result


def _split_aged(jobs: list[Job], config: dict[str, Any]) -> tuple[list[Job], list[Job]]:
    """The portal jobs past portal_max_age_days, and the ones left (all of them when it is off)."""
    max_age = int(config.get("portal_max_age_days") or 0)
    if max_age <= 0:
        return [], jobs
    cutoff = datetime.now() - timedelta(days=max_age)  # noqa: DTZ005 - the database stores naive local time
    aged = [job for job in jobs if job.found_at < cutoff]
    return aged, [job for job in jobs if job not in aged]


def _tally_portal_jobs(
    source: str,
    jobs: list[Job],
    *,
    config: dict[str, Any],
    result: StalenessResult,
    portal_counts: dict[str, int],
) -> None:
    """Age out what is old enough, and count the rest: a portal feed has no listing to re-check."""
    aged, remaining = _split_aged(jobs, config)
    result.stale_by_age.extend(aged)
    if remaining:
        portal_counts[source] = portal_counts.get(source, 0) + len(remaining)


def _portal_notes(portal_counts: dict[str, int]) -> list[str]:
    return [
        f"{count} {source} job(s) (portal feed, no per-company listing)"
        for source, count in sorted(portal_counts.items())
    ]


async def _run_plugin_checker(
    check: Callable[[], Awaitable[None]], source: str, company: str, *, result: StalenessResult
) -> None:
    # Plugin-provided (untrusted, unlike the first-party _check_via_listing) --
    # guard the call so one misbehaving checker can't abort the whole run.
    try:
        await check()
    except Exception as error:
        logger.warning(
            "staleness: %s checker failed for %s — %s",
            source,
            company,
            error,
            exc_info=True,
        )
        if company not in result.failed_companies:
            result.failed_companies.append(company)


async def _check_via_listing(
    source: str,
    company: str,
    jobs: list[Job],
    *,
    scanners: dict[str, BaseScanner],
    result: StalenessResult,
) -> None:
    scanner = scanners[source]
    # The HTTP scanners never raise: gather_jobs swallows a failed fetch, counts
    # it in stats[source].errors and returns [] -- which, read as "zero open
    # postings", archived a live job after a transient 404 (2026-09-16). The
    # exception guard below stays for scanners that do raise; the stats dict is
    # how the first-party ones report the same failure.
    stats: ScanStats = {}
    try:
        raw: object = await scanner.scan([company], stats=stats)
    except Exception as error:
        logger.warning(
            "staleness: %s scan failed for %s — %s", source, company, error, exc_info=True
        )
        result.failed_companies.append(company)
        return
    if not isinstance(raw, list):
        logger.warning("staleness: %s scan returned unexpected type for %s", source, company)
        result.failed_companies.append(company)
        return
    if (source_stats := stats.get(source)) is not None and source_stats.errors:
        logger.warning(
            "staleness: %s fetch failed for %s (%d error(s)) — not treated as closed",
            source,
            company,
            source_stats.errors,
        )
        result.failed_companies.append(company)
        return
    # Stored job.url is normalized (`normalize_job_url` strips the Recruitee /c/new apply
    # suffix), but the fresh listing's raw URLs are not — normalize both sides,
    # or every freshly-stored Recruitee job compares unequal and is archived
    # as stale on its very first re-scan.
    open_urls = {normalize_job_url(raw_job.url) for raw_job in raw}
    result.stale.extend(job for job in jobs if normalize_job_url(job.url) not in open_urls)
