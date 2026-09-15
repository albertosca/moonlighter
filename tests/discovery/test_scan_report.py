from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.core.db import Job, ScanLog, init_db
from moonlighter.discovery.results import ScanReport, render_scan_report
from moonlighter.discovery.service import _format_report, scan_company

from tests.discovery.test_service import _raw


@pytest.fixture
def three_jobs(tmp_db):
    init_db()
    return [
        Job.create(
            source="greenhouse",
            company="Acme",
            title="Staff Engineer",
            url="https://boards.greenhouse.io/acme/jobs/1",
            score=9.0,
            status="new",
        ),
        Job.create(
            source="greenhouse",
            company="Acme",
            title="Intern",
            url="https://boards.greenhouse.io/acme/jobs/2",
            score=2.0,
            status="rejected",
        ),
        Job.create(
            source="greenhouse",
            company="Acme",
            title="Recruiter",
            url="https://boards.greenhouse.io/acme/jobs/3",
            score=0.0,
            status="rejected",
            score_notes="title filtered: recruiter",
        ),
    ]


def test_format_report_above_threshold_is_unchanged(three_jobs, snapshot_text):
    snapshot_text(_format_report(three_jobs, spend_hit=False, threshold=7.0), "above_threshold")


def test_format_report_none_above_threshold_is_unchanged(three_jobs, snapshot_text):
    snapshot_text(_format_report(three_jobs[1:], spend_hit=False, threshold=7.0), "none_above")


def test_format_report_spend_hit_is_unchanged(three_jobs, snapshot_text):
    snapshot_text(_format_report(three_jobs, spend_hit=True, threshold=7.0), "spend_hit")


def test_render_scan_report_reproduces_the_old_format_report(three_jobs, snapshot_text):
    report = ScanReport(saved=three_jobs, spend_hit=False, threshold=7.0)
    snapshot_text(render_scan_report(report), "above_threshold")


def test_render_scan_report_appends_the_warning_last(three_jobs):
    report = ScanReport(
        saved=three_jobs, spend_hit=False, threshold=7.0, warning="⚠️  linkedin: 0 jobs"
    )
    assert render_scan_report(report).endswith("\n\n⚠️  linkedin: 0 jobs")


def test_render_scan_report_no_new_jobs_is_the_old_literal_string(snapshot_text):
    # Set only when scan_and_evaluate found zero candidates to evaluate at all.
    report = ScanReport(saved=[], spend_hit=False, threshold=7.0, no_new_jobs=True)
    snapshot_text(render_scan_report(report), "empty")


def test_render_scan_report_empty_saved_without_no_new_jobs_still_computes_counts():
    # Distinct from the case above: evaluation was attempted (e.g. a crash, a
    # spend-limit stop, or a silently-skipped IntegrityError) and zero jobs
    # survived it -- must render the computed "0 jobs processed..." counts,
    # matching _format_report([], ...), not the "No new jobs found." literal.
    report = ScanReport(saved=[], spend_hit=True, threshold=7.0)
    rendered = render_scan_report(report)
    assert rendered == _format_report([], spend_hit=True, threshold=7.0)
    assert "jobs processed" in rendered
    assert "No new jobs found." not in rendered


def test_render_scan_report_error_short_circuits_everything_else(three_jobs):
    report = ScanReport(
        saved=three_jobs,
        spend_hit=False,
        threshold=7.0,
        tip="Tip: ignored",
        warning="ignored too",
        error="Unknown source 'bogus'.",
    )
    assert render_scan_report(report) == "Unknown source 'bogus'."


def test_render_scan_report_appends_the_tip_before_archive_and_warning(three_jobs):
    from moonlighter.discovery.archive import ArchiveResult

    report = ScanReport(
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


# ── scan_company's four output shapes (baseline, pinned before restructuring) ─

CONFIG = {"score_threshold": 7.0, "scan_concurrency": 2}


def _patched_scanner(raw_jobs):
    """build_http_scanners() returns {source: scanner}; scanner.scan() is async."""
    scanner = MagicMock()
    scanner.scan = AsyncMock(return_value=list(raw_jobs))
    return patch(
        "moonlighter.discovery.service.build_http_scanners",
        return_value={"greenhouse": scanner},
    )


async def test_scan_company_unknown_source_is_unchanged(tmp_db, snapshot_text):
    init_db()
    with _patched_scanner([]):
        out = await scan_company("lever", "acme", CONFIG, {}, MagicMock())
    snapshot_text(out, "company_unknown_source")


async def test_scan_company_no_open_jobs_is_unchanged(tmp_db, snapshot_text):
    init_db()
    with _patched_scanner([]):
        out = await scan_company("greenhouse", "acme", CONFIG, {}, MagicMock())
    snapshot_text(out, "company_no_open_jobs")


async def test_scan_company_all_already_known_is_unchanged(tmp_db, snapshot_text):
    init_db()
    known = _raw(1)  # url is https://x.com/scan/1
    # _drop_already_seen only checks ScanLog, not Job -- a Job row alone would
    # NOT dedupe this URL and the test would silently fall through to a real
    # evaluate_job() call instead of exercising the "all already known" branch.
    ScanLog.create(job_url=known.url, source="greenhouse")
    with _patched_scanner([known]):
        out = await scan_company("greenhouse", "acme", CONFIG, {}, MagicMock())
    snapshot_text(out, "company_all_known")


async def test_scan_company_with_new_jobs_is_unchanged(tmp_db, snapshot_text, three_jobs):
    init_db()
    fresh = _raw(99)
    with (
        _patched_scanner([fresh]),
        patch(
            "moonlighter.discovery.service._evaluate_and_store",
            new=AsyncMock(return_value=(three_jobs, False)),
        ),
    ):
        out = await scan_company("greenhouse", "acme", CONFIG, {}, MagicMock())
    snapshot_text(out, "company_new_jobs")
