"""The rendered text of every scan shape, pinned as snapshots (tests/snapshots/test_scan_report.*)."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import ScanLog, init_db
from moonlighter.discovery.scan.results import (
    ScanKind,
    ScanReport,
    _render_counts,
    render_scan_report,
)
from moonlighter.discovery.scan.scanning import scan_company
from moonlighter.discovery.sources.base import SourceStats

from tests.discovery.scan_fakes import make_raw_job, run_scan

CONFIG = {"score_threshold": 7.0, "scan_concurrency": 2}


def _patched_scanner(raw_jobs):
    """build_http_scanners() returns {source: scanner}; scanner.scan() is async."""
    scanner = MagicMock()
    scanner.scan = AsyncMock(return_value=list(raw_jobs))
    return patch(
        "moonlighter.discovery.scan.scanning.build_http_scanners",
        return_value={"greenhouse": scanner},
    )


def test_scan_report_company_is_a_fact_not_a_mode_switch(three_jobs, snapshot_text):
    # Before: ScanReport(kind=ScanKind.EVALUATED, saved=[...], company="acme") rendered "No open jobs
    # found at 'acme'" and dropped the whole table. Now scan_company can name
    # the company it scanned on its evaluated shape too, and the output is
    # the same bytes as with no company at all.
    report = ScanReport(kind=ScanKind.EVALUATED, saved=three_jobs, threshold=7.0, company="acme")
    snapshot_text(render_scan_report(report), "above_threshold")


def test_render_counts_above_threshold_is_unchanged(three_jobs, snapshot_text):
    report = ScanReport(kind=ScanKind.EVALUATED, saved=three_jobs, spend_hit=False, threshold=7.0)
    snapshot_text(_render_counts(report), "above_threshold")


def test_render_counts_none_above_threshold_is_unchanged(three_jobs, snapshot_text):
    report = ScanReport(
        kind=ScanKind.EVALUATED, saved=three_jobs[1:], spend_hit=False, threshold=7.0
    )
    snapshot_text(_render_counts(report), "none_above")


def test_render_counts_spend_hit_is_unchanged(three_jobs, snapshot_text):
    report = ScanReport(kind=ScanKind.EVALUATED, saved=three_jobs, spend_hit=True, threshold=7.0)
    snapshot_text(_render_counts(report), "spend_hit")


def test_render_scan_report_reproduces_the_old_format_report(three_jobs, snapshot_text):
    report = ScanReport(kind=ScanKind.EVALUATED, saved=three_jobs, spend_hit=False, threshold=7.0)
    snapshot_text(render_scan_report(report), "above_threshold")


def test_render_scan_report_no_new_jobs_is_the_old_literal_string(snapshot_text):
    # Set only when scan_and_evaluate found zero candidates to evaluate at all.
    report = ScanReport(kind=ScanKind.NO_NEW_JOBS, threshold=7.0)
    snapshot_text(render_scan_report(report), "empty")


def test_scan_report_stats_is_not_rendered(three_jobs, snapshot_text):
    # The MCP output must not move: stats is for the JSON consumer only.

    report = ScanReport(
        kind=ScanKind.EVALUATED,
        saved=three_jobs,
        threshold=7.0,
        stats={"greenhouse": SourceStats(companies=1, jobs=3, errors=0)},
    )
    snapshot_text(render_scan_report(report), "above_threshold")


async def test_scan_company_unknown_source_is_unchanged(temporary_database, snapshot_text):
    init_db()
    with _patched_scanner([]):
        out = render_scan_report(
            await scan_company("lever", "acme", CONFIG, profile={}, caller=MagicMock())
        )
    snapshot_text(out, "company_unknown_source")


async def test_scan_company_no_open_jobs_is_unchanged(temporary_database, snapshot_text):
    init_db()
    with _patched_scanner([]):
        out = render_scan_report(
            await scan_company("greenhouse", "acme", CONFIG, profile={}, caller=MagicMock())
        )
    snapshot_text(out, "company_no_open_jobs")


async def test_scan_company_all_already_known_is_unchanged(temporary_database, snapshot_text):
    init_db()
    known = make_raw_job(1)  # url is https://x.com/scan/1
    # drop_already_seen only checks ScanLog, not Job -- a Job row alone would
    # NOT dedupe this URL and the test would silently fall through to a real
    # evaluate_job() call instead of exercising the "all already known" branch.
    ScanLog.create(job_url=known.url, source="greenhouse")
    with _patched_scanner([known]):
        out = render_scan_report(
            await scan_company("greenhouse", "acme", CONFIG, profile={}, caller=MagicMock())
        )
    snapshot_text(out, "company_all_known")


async def test_scan_company_with_new_jobs_is_unchanged(
    temporary_database, snapshot_text, three_jobs
):
    init_db()
    fresh = make_raw_job(99)
    with (
        _patched_scanner([fresh]),
        patch(
            "moonlighter.discovery.scan.scanning.evaluate_and_store",
            new=AsyncMock(return_value=(three_jobs, False)),
        ),
    ):
        out = render_scan_report(
            await scan_company("greenhouse", "acme", CONFIG, profile={}, caller=MagicMock())
        )
    snapshot_text(out, "company_new_jobs")


async def test_scan_and_evaluate_end_to_end_pins_the_full_output_with_archive(
    temporary_database, snapshot_text
):
    init_db()
    out = await run_scan([make_raw_job(1)])
    snapshot_text(out, "scan_and_evaluate_end_to_end")
