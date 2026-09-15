"""The structured result of a scan, and the renderer that prints it.

The service computes; the renderer formats. The MCP server calls the renderer
so its output is unchanged, and a CLI can serialise the same dataclass as JSON
without either side owning the other's format.
"""

from dataclasses import dataclass

from moonlighter.core.db import Job
from moonlighter.discovery.archive import ArchiveResult, _format_archive_result
from moonlighter.views import render_jobs_table


@dataclass(frozen=True)
class ScanReport:
    saved: list[Job]
    spend_hit: bool
    threshold: float
    archive: ArchiveResult | None = None
    warning: str | None = None
    tip: str | None = None
    error: str | None = None
    # Only scan_company can distinguish "nothing new, but N were found and are
    # already known" from "nothing found at all" -- an empty raw_jobs there may
    # mean zero open postings OR a failed fetch.
    found_but_known: int = 0
    # Set only by scan_company, only on its two "nothing new" shapes (never on
    # its own "new jobs found" shape, and never by scan_and_evaluate, which has
    # no single company to name). This is the signal _render_counts uses to
    # pick one of scan_company's literal sentences instead of the generic
    # "N jobs processed..." counts -- found_but_known alone can't do it, since
    # 0 is also scan_and_evaluate's default and would collide with "no open
    # jobs found at <company>" for zero raw_jobs.
    company: str | None = None
    # True only when there were zero candidate jobs to evaluate in the first
    # place (no_new_jobs is the ONLY thing distinguishing that from "evaluated
    # some candidates but zero survived" -- a crash, a spend-limit stop, or a
    # silently-skipped IntegrityError all also leave saved=[], and those must
    # still render the computed "N jobs processed..." counts, not this literal.
    # scan_and_evaluate is the only caller that sets it.
    no_new_jobs: bool = False


def render_scan_report(report: ScanReport) -> str:
    if report.error is not None:
        return report.error
    body = "No new jobs found." if report.no_new_jobs else _render_counts(report)
    if report.tip is not None:
        body += f"\n\n{report.tip}"
    if report.archive is not None:
        body += f"\n\n{_format_archive_result(report.archive)}"
    if report.warning is not None:
        body += f"\n\n{report.warning}"
    return body


def _render_counts(report: ScanReport) -> str:
    if report.company is not None:
        # scan_company's two "nothing new" shapes: no evaluation was attempted
        # (new_jobs was empty), so there are no counts to compute at all.
        if report.found_but_known:
            return (
                f"No new jobs at {report.company!r} "
                f"({report.found_but_known} found, all already known)."
            )
        return f"No open jobs found at {report.company!r} (see warnings below if the fetch failed)."

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
