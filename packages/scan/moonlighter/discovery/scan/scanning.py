"""The two scans: every configured company (`scan_and_evaluate`) and one company (`scan_company`)."""

from typing import Any

from moonlighter.core.config.company_list import load_company_list
from moonlighter.core.db import Job
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.discovery.archive import archive_stale_jobs
from moonlighter.discovery.scan.claims import drop_already_seen
from moonlighter.discovery.scan.collection import collect_raw_jobs, normalize_urls
from moonlighter.discovery.scan.pipeline import evaluate_and_store
from moonlighter.discovery.scan.results import ScanKind, ScanReport
from moonlighter.discovery.scan.source_warnings import stats_warnings
from moonlighter.discovery.screening.no_eval import NoEval
from moonlighter.discovery.sources.base import BaseScanner, ScanStats
from moonlighter.discovery.sources.registry import build_http_scanners


async def scan_and_evaluate(  # noqa: PLR0917 - pinned by tests/discovery/test_cli.py:105
    keywords: str,
    phase: str,
    config: dict[str, Any],
    profile: dict[str, Any],
    caller: LLMCaller | NoEval,
) -> ScanReport:
    """Scan every configured source, evaluate what no earlier scan saw, and archive stale jobs."""
    companies = load_company_list(phase=None if phase == "all" else phase)
    stats: ScanStats = {}
    raw_jobs, warning = await collect_raw_jobs(keywords, config, companies, stats=stats)
    new_jobs = drop_already_seen(raw_jobs)
    saved: list[Job] = []
    spend_hit = False
    if new_jobs:
        saved, spend_hit = await evaluate_and_store(new_jobs, config, profile, caller=caller)
    return ScanReport(
        kind=ScanKind.EVALUATED if new_jobs else ScanKind.NO_NEW_JOBS,
        saved=saved,
        spend_hit=spend_hit,
        threshold=config["score_threshold"],
        archive=await archive_stale_jobs(None, None, config),
        warning=warning,
        stats=stats,
    )


def _unknown_source_report(
    source: str, threshold: float, scanners: dict[str, BaseScanner]
) -> ScanReport:
    return ScanReport(
        kind=ScanKind.UNKNOWN_SOURCE,
        threshold=threshold,
        error=(
            f"Unknown source {source!r}. Valid sources: {', '.join(sorted(scanners))}. "
            "Portal boards (gupy, remoteok, remotive, weworkremotely, hn_whoishiring) "
            "are enabled via config flags and scanned by scan_and_evaluate."
        ),
    )


async def scan_company(
    source: str,
    company: str,
    config: dict[str, Any],
    *,
    profile: dict[str, Any],
    caller: LLMCaller | NoEval,
) -> ScanReport:
    """Scan every open posting at ONE company right now, without touching company_list.yaml.

    `company` is an ATS slug, or (Recruitee) a custom career domain.
    """
    threshold = config["score_threshold"]
    scanners = build_http_scanners()
    if source not in scanners:
        return _unknown_source_report(source, threshold, scanners)
    stats: ScanStats = {}
    raw_jobs = normalize_urls(await scanners[source].scan([company], stats=stats))
    new_jobs = drop_already_seen(raw_jobs)
    tip = (
        f"Tip: add {company!r} under '{source}:' in company_list.yaml "
        "to include it in recurring scans."
    )
    warning = "\n".join(stats_warnings(stats)) or None

    if new_jobs:
        saved, spend_hit = await evaluate_and_store(new_jobs, config, profile, caller=caller)
        return ScanReport(
            kind=ScanKind.EVALUATED,
            saved=saved,
            spend_hit=spend_hit,
            threshold=threshold,
            tip=tip,
            warning=warning,
            company=company,
            stats=stats,
        )

    # An empty raw_jobs can mean the company genuinely has zero open postings
    # OR the fetch itself failed -- found_but_known (0 here, len(raw_jobs)
    # otherwise) lets the renderer pick the right sentence without lying about
    # which happened; `warning` (via stats_warnings) carries the fetch-error
    # detail when there is one.
    return ScanReport(
        kind=ScanKind.ALL_KNOWN if raw_jobs else ScanKind.NO_OPEN_JOBS,
        threshold=threshold,
        tip=tip,
        warning=warning,
        company=company,
        found_but_known=len(raw_jobs),
        stats=stats,
    )
