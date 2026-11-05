"""Collecting the raw jobs of one scan: HTTP boards, browser plugins and portal feeds."""

from dataclasses import replace
from typing import Any

from moonlighter.core.plugins import discover_entry_points
from moonlighter.core.web.urls import normalize_job_url
from moonlighter.discovery.portals import scan_portals
from moonlighter.discovery.source_warnings import stats_warnings
from moonlighter.discovery.sources.base import (
    BaseScanner,
    RawJob,
    ScannerSessionExpiredError,
    ScanStats,
)
from moonlighter.discovery.sources.registry import build_http_scanners


async def _run_browser_scanner(
    scanner_class: type[Any], keywords: str, config: dict[str, Any]
) -> tuple[list[RawJob], str | None]:
    """Run one browser-based scanner plugin (requires prior login, same shape as LinkedInScanner).

    An expired session becomes a warning; any other failure, including no
    browser being available, is silent so it doesn't block the HTTP results.
    """
    try:
        from moonlighter.core import browser  # noqa: PLC0415 - playwright is an optional extra

        page = await browser.new_page(config)
    except Exception:  # noqa: BLE001 - a missing browser must never block the HTTP results
        return [], None
    try:
        jobs = await scanner_class(page).scan(keywords=keywords)
    except ScannerSessionExpiredError as error:
        label = scanner_class.__name__.removesuffix("Scanner")
        return [], f"⚠️  {label}: {error}"
    except Exception:  # noqa: BLE001 - one broken plugin must never block the other sources
        return [], None
    else:
        return jobs, None
    finally:
        await page.close()


def _unknown_source_warnings(
    companies: dict[str, list[str]], scanners: dict[str, BaseScanner]
) -> list[str]:
    return [
        f"⚠️  company_list.yaml: unknown source {unknown!r} — no scanner with that name, "
        "entries ignored"
        for unknown in sorted(set(companies) - set(scanners))
    ]


async def _scan_boards(
    scanners: dict[str, BaseScanner], companies: dict[str, list[str]], stats: ScanStats
) -> list[RawJob]:
    raw_jobs: list[RawJob] = []
    for source, scanner in scanners.items():
        slugs = companies.get(source, [])
        if slugs:
            raw_jobs.extend(await scanner.scan(slugs, stats=stats))
    return raw_jobs


async def _run_plugins(keywords: str, config: dict[str, Any]) -> tuple[list[RawJob], list[str]]:
    raw_jobs: list[RawJob] = []
    warnings: list[str] = []
    for scanner_class in discover_entry_points("moonlighter.scanners"):
        jobs, warning = await _run_browser_scanner(scanner_class, keywords, config)
        raw_jobs.extend(jobs)
        if warning:
            warnings.append(warning)
    return raw_jobs, warnings


def _gupy_warnings(config: dict[str, Any], keywords: str) -> list[str]:
    if config.get("scan_gupy") and not keywords.strip():
        return [
            (
                "⚠️  scan_gupy is on but no keywords were given: Gupy is a keyword feed and "
                "moonlighter has no built-in search term, so it was skipped. Pass keywords."
            )
        ]
    return []


def normalize_urls(raw_jobs: list[RawJob]) -> list[RawJob]:
    """The same raw jobs with each URL normalised, so one posting has one identity."""
    return [replace(raw_job, url=normalize_job_url(raw_job.url)) for raw_job in raw_jobs]


async def collect_raw_jobs(
    keywords: str,
    config: dict[str, Any],
    companies: dict[str, list[str]],
    *,
    stats: ScanStats | None = None,
) -> tuple[list[RawJob], str | None]:
    """Collect jobs from the HTTP sources and every registered browser-scanner plugin.

    Returns the raw jobs and any warnings -- from the browser scanners plus one
    line per HTTP/portal source that errored or came back empty -- joined into
    one string.
    """
    scanners = build_http_scanners()
    warnings = _unknown_source_warnings(companies, scanners)
    if stats is None:
        stats = {}
    raw_jobs = await _scan_boards(scanners, companies, stats)
    plugin_jobs, plugin_warnings = await _run_plugins(keywords, config)
    raw_jobs.extend(plugin_jobs)
    warnings.extend(plugin_warnings)
    warnings.extend(_gupy_warnings(config, keywords))
    raw_jobs.extend(await scan_portals(config, stats, keywords))
    warnings.extend(stats_warnings(stats))
    return normalize_urls(raw_jobs), ("\n".join(warnings) or None)
