"""Rendering the scan counts line, including the needs-review verify note."""

from moonlighter.core.db import init_db
from moonlighter.discovery.scan.results import ScanKind, ScanReport, _render_counts
from tests.discovery.scan.results.saved_jobs import saved_job


async def test_render_counts_needs_review_separately_from_below(temporary_database):
    init_db()
    above = saved_job("https://x.com/fr/1", status="new", score=8.0)
    below = saved_job("https://x.com/fr/2", status="archived", score=3.0)
    pending = saved_job(
        "https://x.com/fr/3",
        status="needs_review",
        score=None,
        score_notes="description unavailable — needs manual verification",
    )
    report = _render_counts(
        ScanReport(
            kind=ScanKind.EVALUATED, saved=[above, below, pending], spend_hit=False, threshold=6.5
        )
    )
    assert "1 below threshold" in report
    assert "1 job(s) need manual verification" in report
    assert "list_jobs(status='needs_review')" in report
    assert "verify_job(job_id, page_text)" in report


async def test_render_counts_no_verify_line_when_nothing_pending(temporary_database):
    init_db()
    above = saved_job("https://x.com/fr/4", status="new", score=8.0)
    report = _render_counts(
        ScanReport(kind=ScanKind.EVALUATED, saved=[above], spend_hit=False, threshold=6.5)
    )
    assert "need manual verification" not in report


async def test_render_counts_verify_line_shown_even_with_nothing_above_threshold(
    temporary_database,
):
    init_db()
    pending = saved_job(
        "https://x.com/fr/5",
        status="needs_review",
        score=None,
        score_notes="description unavailable — needs manual verification",
    )
    report = _render_counts(
        ScanReport(kind=ScanKind.EVALUATED, saved=[pending], spend_hit=False, threshold=6.5)
    )
    assert "None passed the threshold" in report
    assert "1 job(s) need manual verification" in report


async def test_render_counts_verify_note_is_pinned_exactly(temporary_database):
    init_db()
    pending = saved_job(
        "https://x.com/fr/5",
        status="needs_review",
        score=None,
        score_notes="description unavailable — needs manual verification",
    )
    report = _render_counts(
        ScanReport(kind=ScanKind.EVALUATED, saved=[pending], spend_hit=False, threshold=6.5)
    )
    assert report == (
        "1 jobs processed. None passed the threshold of 6.5. "
        "(0 filtered by title, 0 location ineligible, 0 below score)\n\n"
        "⚠️  1 job(s) need manual verification — "
        "list_jobs(status='needs_review') to see them, verify_job(job_id, page_text) to score one."
    )
