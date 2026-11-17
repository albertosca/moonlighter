"""What render_scan_report appends and in which order, asserted on the text itself."""

from moonlighter.discovery.archive import ArchiveResult
from moonlighter.discovery.scan.results import (
    ScanKind,
    ScanResult,
    _render_counts,
    render_scan_report,
)
from moonlighter.discovery.unanswered import UnansweredResult


def test_render_scan_report_appends_the_warning_last(three_jobs):
    report = ScanResult(
        kind=ScanKind.EVALUATED,
        saved=three_jobs,
        spend_hit=False,
        threshold=7.0,
        warning="⚠️  linkedin: 0 jobs",
    )
    assert render_scan_report(report).endswith("\n\n⚠️  linkedin: 0 jobs")


def test_render_scan_report_empty_saved_without_no_new_jobs_still_computes_counts():
    # Distinct from the case above: evaluation was attempted (e.g. a crash, a
    # spend-limit stop, or a silently-skipped IntegrityError) and zero jobs
    # survived it -- must render the computed "0 jobs processed..." counts,
    # matching _render_counts([], ...), not the "No new jobs found." literal.
    report = ScanResult(kind=ScanKind.EVALUATED, saved=[], spend_hit=True, threshold=7.0)
    rendered = render_scan_report(report)
    assert rendered == _render_counts(
        ScanResult(kind=ScanKind.EVALUATED, saved=[], spend_hit=True, threshold=7.0)
    )
    assert "jobs processed" in rendered
    assert "No new jobs found." not in rendered


def test_render_scan_report_error_short_circuits_everything_else(three_jobs):
    report = ScanResult(
        kind=ScanKind.UNKNOWN_SOURCE,
        threshold=7.0,
        tip="Tip: ignored",
        warning="ignored too",
        error="Unknown source 'bogus'.",
    )
    assert render_scan_report(report) == "Unknown source 'bogus'."


def test_render_scan_report_appends_the_tip_before_archive_and_warning(three_jobs):

    report = ScanResult(
        kind=ScanKind.EVALUATED,
        saved=three_jobs,
        spend_hit=False,
        threshold=7.0,
        tip="Tip: add it to company_list.yaml",
        archive=ArchiveResult(),
        warning="⚠️  linkedin: 0 jobs",
    )
    rendered = render_scan_report(report)
    tip_at = rendered.index("Tip: add it to company_list.yaml")
    archive_at = rendered.index("No closed jobs found.")
    warning_at = rendered.index("⚠️  linkedin: 0 jobs")
    assert tip_at < archive_at < warning_at


def test_render_scan_report_appends_the_unanswered_section_after_the_archive():
    report = ScanResult(
        kind=ScanKind.NO_NEW_JOBS,
        archive=ArchiveResult(),
        unanswered=UnansweredResult(ran=False, last_sync=None),
    )
    rendered = render_scan_report(report)
    assert rendered.endswith(
        "\n\nNo-response rule did not run: there is no complete email sync yet. "
        "Run sync_email_responses first."
    )


def test_render_scan_report_skips_an_unanswered_section_with_nothing_to_say():
    plain = render_scan_report(ScanResult(kind=ScanKind.NO_NEW_JOBS))
    quiet = render_scan_report(
        ScanResult(
            kind=ScanKind.NO_NEW_JOBS,
            unanswered=UnansweredResult(ran=True, last_sync="2026-11-16T10:00:00"),
        )
    )
    assert quiet == plain
