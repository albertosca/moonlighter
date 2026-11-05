"""What render_scan_report appends and in which order, asserted on the text itself."""

from moonlighter.discovery.archive import ArchiveResult
from moonlighter.discovery.results import ScanKind, ScanReport, _render_counts, render_scan_report


def test_render_scan_report_appends_the_warning_last(three_jobs):
    report = ScanReport(
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
    report = ScanReport(kind=ScanKind.EVALUATED, saved=[], spend_hit=True, threshold=7.0)
    rendered = render_scan_report(report)
    assert rendered == _render_counts(
        ScanReport(kind=ScanKind.EVALUATED, saved=[], spend_hit=True, threshold=7.0)
    )
    assert "jobs processed" in rendered
    assert "No new jobs found." not in rendered


def test_render_scan_report_error_short_circuits_everything_else(three_jobs):
    report = ScanReport(
        kind=ScanKind.UNKNOWN_SOURCE,
        threshold=7.0,
        tip="Tip: ignored",
        warning="ignored too",
        error="Unknown source 'bogus'.",
    )
    assert render_scan_report(report) == "Unknown source 'bogus'."


def test_render_scan_report_appends_the_tip_before_archive_and_warning(three_jobs):

    report = ScanReport(
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
