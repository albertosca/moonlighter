"""Rendering the scan counts line: location-ineligible jobs and the order of the notes."""

from moonlighter.core.db import init_db
from moonlighter.discovery.scan.results import ScanKind, ScanReport, _render_counts

from tests.discovery.scan.results.saved_jobs import saved_job

SPEND_NOTE = (
    "\n\n⚠️  Spend limit reached — scan stopped (remaining jobs are left for the next scan)."
)
VERIFY_NOTE = (
    "\n\n⚠️  1 job(s) need manual verification — "
    "list_jobs(status='needs_review') to see them, verify_job(job_id, page_text) to score one."
)


def _ineligible_job(url):
    return saved_job(
        url, status="archived", score=0.0, score_notes="location ineligible: 'Bangalore, India'"
    )


def _needs_review_job(url):
    return saved_job(url, status="needs_review", score=None, score_notes="unscored")


async def test_render_counts_names_location_ineligible_jobs_when_none_pass(temporary_database):
    init_db()
    saved = [_ineligible_job("https://x.com/loc/1"), _ineligible_job("https://x.com/loc/2")]
    report = _render_counts(ScanReport(kind=ScanKind.EVALUATED, saved=saved, threshold=6.5))
    assert report == (
        "2 jobs processed. None passed the threshold of 6.5. "
        "(0 filtered by title, 2 location ineligible, 0 below score)"
    )


async def test_render_counts_names_location_ineligible_jobs_in_the_footer(temporary_database):
    init_db()
    saved = [saved_job("https://x.com/loc/3"), _ineligible_job("https://x.com/loc/4")]
    report = _render_counts(ScanReport(kind=ScanKind.EVALUATED, saved=saved, threshold=6.5))
    assert report.startswith("2 jobs processed. 1 above threshold:\n\n")
    assert report.endswith(
        "\n∗ = salary estimated by the LLM  |  "
        "0 below threshold  |  0 filtered by title  |  1 location ineligible"
    )


async def test_render_counts_puts_the_spend_note_before_the_verify_note_when_none_pass(
    temporary_database,
):
    init_db()
    saved = [_needs_review_job("https://x.com/loc/5")]
    report = _render_counts(
        ScanReport(kind=ScanKind.EVALUATED, saved=saved, spend_hit=True, threshold=6.5)
    )
    assert report.endswith(
        "(0 filtered by title, 0 location ineligible, 0 below score)" + SPEND_NOTE + VERIFY_NOTE
    )


async def test_render_counts_puts_the_spend_note_before_the_verify_note_after_the_footer(
    temporary_database,
):
    init_db()
    saved = [saved_job("https://x.com/loc/6"), _needs_review_job("https://x.com/loc/7")]
    report = _render_counts(
        ScanReport(kind=ScanKind.EVALUATED, saved=saved, spend_hit=True, threshold=6.5)
    )
    assert report.endswith(
        "0 below threshold  |  0 filtered by title  |  0 location ineligible"
        + SPEND_NOTE
        + VERIFY_NOTE
    )
