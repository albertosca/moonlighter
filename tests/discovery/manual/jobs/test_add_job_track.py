"""add_job track=True: a job the person already chose is scored for the record, never archived."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.manual.jobs import add_job
from tests.discovery.fake_scan import CONFIG, PROFILE, evaluation_result

URL = "https://x.com/track/1"
KEPT_LINE = (
    "Kept on purpose (track=True): stored as reviewed whatever the score, "
    "so the archive does not hide it."
)


def _evaluating(score):
    return patch(
        "moonlighter.discovery.manual.jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(score)),
    )


async def test_track_keeps_a_below_threshold_job_reviewed_with_its_score(temporary_database):
    init_db()
    with _evaluating(5.0):
        message = await add_job(
            URL, "Solides", "AI Analyst", "desc", CONFIG, PROFILE, MagicMock(), track=True
        )
    job = Job.get(Job.url == URL)
    assert (job.status, job.score) == ("reviewed", 5.0)
    assert message.startswith("✓ KEPT — Solides / AI Analyst\n")
    assert message.endswith(f"id={job.id}\n{KEPT_LINE}")


async def test_track_bypasses_the_title_filter(temporary_database):
    init_db()
    with _evaluating(5.0) as evaluator:
        await add_job(
            URL, "Acme", "Staff Accountant", "desc", CONFIG, PROFILE, MagicMock(), track=True
        )
    assert evaluator.await_count == 1
    assert Job.get(Job.url == URL).status == "reviewed"


async def test_without_track_a_below_threshold_job_is_archived(temporary_database):
    init_db()
    with _evaluating(5.0):
        message = await add_job(URL, "Solides", "AI Analyst", "desc", CONFIG, PROFILE, MagicMock())
    assert Job.get(Job.url == URL).status == "archived"
    assert KEPT_LINE not in message
