"""A copy archived against a stored job is counted as a duplicate, not as below score."""

from moonlighter.core.db import init_db
from moonlighter.discovery.scan.results import ScanKind, ScanResult, _render_counts
from tests.discovery.scan.results.saved_jobs import saved_job


def _copy(url):
    return saved_job(url, status="archived", score=0.0, score_notes="duplicate of #3")


async def test_a_duplicate_is_counted_apart_when_none_pass(temporary_database):
    init_db()
    saved = [_copy("https://x.com/dup/1"), saved_job("https://x.com/dup/2", status="archived")]
    report = _render_counts(ScanResult(kind=ScanKind.EVALUATED, saved=saved, threshold=6.5))
    assert report == (
        "2 jobs processed. None passed the threshold of 6.5. "
        "(0 filtered by title, 0 location ineligible, 1 duplicates, 1 below score)"
    )


async def test_a_duplicate_is_counted_apart_in_the_footer(temporary_database):
    init_db()
    saved = [saved_job("https://x.com/dup/3"), _copy("https://x.com/dup/4")]
    report = _render_counts(ScanResult(kind=ScanKind.EVALUATED, saved=saved, threshold=6.5))
    assert report.endswith(
        "0 below threshold  |  0 filtered by title  |  0 location ineligible  |  1 duplicates"
    )
