"""The structured result of a scan, and the renderer that prints it.

The service computes; the renderer formats. The MCP server calls the renderer
so its output is unchanged, and a CLI can serialise the same dataclass as JSON
without either side owning the other's format.
"""

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from moonlighter.core.cli import job_to_dict
from moonlighter.core.db import Job
from moonlighter.discovery.archive import ArchiveResult, _format_archive_result
from moonlighter.discovery.sources.base import ScanStats
from moonlighter.views import render_jobs_table


class ScanKind(StrEnum):
    """Which of the five shapes a scan produced. One field, exhaustive, so the
    renderer dispatches on it and a CLI can map it to an exit code without
    parsing the message."""

    EVALUATED = "evaluated"  # candidates were evaluated: saved/spend_hit carry the counts
    NO_NEW_JOBS = "no_new_jobs"  # scan_and_evaluate: nothing to evaluate at all
    ALL_KNOWN = "all_known"  # scan_company: found some, every one already in ScanLog
    NO_OPEN_JOBS = "no_open_jobs"  # scan_company: zero postings (or the fetch failed)
    UNKNOWN_SOURCE = "unknown_source"  # scan_company: usage error, `error` carries it


@dataclass(frozen=True)
class ScanReport:
    kind: ScanKind
    saved: list[Job] = field(default_factory=list)
    spend_hit: bool = False
    threshold: float = 0.0
    archive: ArchiveResult | None = None
    warning: str | None = None
    tip: str | None = None
    error: str | None = None
    # A fact, not a switch: the company scan_company scanned, on every shape.
    company: str | None = None
    # ALL_KNOWN only: how many postings were found and already known.
    found_but_known: int = 0
    # Per-source fetch accounting the service already computes; not rendered
    # -- a CLI's JSON is the only consumer (see scan_report_to_dict).
    stats: ScanStats | None = None

    def __post_init__(self) -> None:
        # Every invariant here is "the fields agree with the kind". Before the
        # kind existed, `company` and `no_new_jobs` were renderer mode switches
        # that silently discarded saved/spend_hit when combined with them; now
        # the contradiction is impossible to express without raising.
        k = self.kind
        if (self.error is not None) != (k is ScanKind.UNKNOWN_SOURCE):
            raise ValueError("ScanReport.error is set exactly when kind is unknown_source")
        if k in (ScanKind.ALL_KNOWN, ScanKind.NO_OPEN_JOBS) and self.company is None:
            raise ValueError(f"ScanReport kind {k} names a company; company is required")
        if (self.found_but_known > 0) != (k is ScanKind.ALL_KNOWN):
            raise ValueError(
                "ScanReport.found_but_known is positive exactly when kind is all_known"
            )
        if k is not ScanKind.EVALUATED and (self.saved or self.spend_hit):
            raise ValueError("only an evaluated ScanReport carries saved/spend_hit")


def render_scan_report(report: ScanReport) -> str:
    if report.error is not None:
        return report.error
    body = _body(report)
    if report.tip is not None:
        body += f"\n\n{report.tip}"
    if report.archive is not None:
        body += f"\n\n{_format_archive_result(report.archive)}"
    if report.warning is not None:
        body += f"\n\n{report.warning}"
    return body


def _body(report: ScanReport) -> str:
    match report.kind:
        case ScanKind.NO_NEW_JOBS:
            return "No new jobs found."
        case ScanKind.ALL_KNOWN:
            return (
                f"No new jobs at {report.company!r} "
                f"({report.found_but_known} found, all already known)."
            )
        case ScanKind.NO_OPEN_JOBS:
            return f"No open jobs found at {report.company!r} (see warnings below if the fetch failed)."
        case _:
            return _render_counts(report)


def _render_counts(report: ScanReport) -> str:
    saved = report.saved
    spend_hit = report.spend_hit
    threshold = report.threshold

    above = [j for j in saved if j.status == "new"]
    title_filtered = sum(
        1 for j in saved if j.score_notes and j.score_notes.startswith("title filtered:")
    )
    location_ineligible = sum(
        1 for j in saved if j.score_notes and j.score_notes.startswith("location ineligible:")
    )
    needs_verification = sum(1 for j in saved if j.status == "needs_review")
    below = len(saved) - len(above) - title_filtered - location_ineligible - needs_verification
    spend_note = (
        "\n\n⚠️  Spend limit reached — scan stopped (remaining jobs are left for the next scan)."
        if spend_hit
        else ""
    )
    verify_note = (
        f"\n\n⚠️  {needs_verification} job(s) need manual verification — "
        f"list_jobs(status='needs_review') to see them, verify_job(job_id, page_text) to score one."
        if needs_verification
        else ""
    )

    if not above:
        return (
            f"{len(saved)} jobs processed. None passed the threshold of {threshold}. "
            f"({title_filtered} filtered by title, {location_ineligible} location ineligible, "
            f"{below} below score)"
            f"{spend_note}{verify_note}"
        )

    table = render_jobs_table(above)
    footer = (
        f"\n∗ = salary estimated by the LLM  |  "
        f"{below} below threshold  |  {title_filtered} filtered by title  |  "
        f"{location_ineligible} location ineligible"
    )
    return (
        f"{len(saved)} jobs processed. {len(above)} above threshold:\n\n{table}{footer}"
        f"{spend_note}{verify_note}"
    )


def scan_report_to_dict(report: ScanReport) -> dict[str, Any]:
    """The JSON a CLI prints. Every fact the renderer uses is here, plus the
    ones it does not (stats): a script reads counts, never sentences."""
    return {
        "kind": report.kind.value,
        "threshold": report.threshold,
        "spend_hit": report.spend_hit,
        "company": report.company,
        "found_but_known": report.found_but_known,
        "saved": [job_to_dict(j) for j in report.saved],
        "archive": asdict(report.archive) if report.archive is not None else None,
        "stats": {k: asdict(v) for k, v in report.stats.items()}
        if report.stats is not None
        else None,
        "warning": report.warning,
        "tip": report.tip,
        "error": report.error,
    }
