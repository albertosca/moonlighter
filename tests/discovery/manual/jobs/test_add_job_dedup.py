"""add_job never saves a URL the database already knows."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Job, ScanLog, init_db
from moonlighter.discovery.manual.jobs import add_job
from tests.discovery.scan_fakes import CONFIG, PROFILE, evaluation_result


async def test_add_job_dedup_existing_job(temporary_database):
    init_db()
    Job.create(
        source="manual",
        company="Stripe",
        title="Eng",
        url="https://x.com/5",
        score=7.2,
        status="new",
    )
    ScanLog.create(job_url="https://x.com/5", source="manual")
    result = await add_job("https://x.com/5", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock())
    assert "already in the database" in result
    assert "score=7.2" in result
    assert "verify_job" not in result


async def test_add_job_dedup_needs_review_job_does_not_crash_on_none_score(temporary_database):
    init_db()
    Job.create(
        source="manual",
        company="Stripe",
        title="Eng",
        url="https://x.com/5b",
        score=None,
        status="needs_review",
    )
    ScanLog.create(job_url="https://x.com/5b", source="manual")
    result = await add_job(
        "https://x.com/5b", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
    )
    assert "already in the database" in result
    assert "score=—" in result
    assert "verify_job" in result


async def test_add_job_scanlog_without_job_proceeds_to_eval(temporary_database):
    init_db()
    # ScanLog has the URL but there's no Job (rare inconsistent state) → dedup lets
    # it through (Job.get raises DoesNotExist), evaluates, but the final ScanLog.create
    # collides with the existing record → IntegrityError → conflict message.
    ScanLog.create(job_url="https://x.com/6", source="manual")
    with patch(
        "moonlighter.discovery.manual.jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(8.0)),
    ):
        result = await add_job(
            "https://x.com/6", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "URL conflict" in result


async def test_add_job_existing_job_messages_are_pinned_exactly(temporary_database):
    init_db()
    scored = Job.create(
        source="manual",
        company="Stripe",
        title="Eng",
        url="https://x.com/pin/7",
        score=7.25,
        status="new",
    )
    ScanLog.create(job_url="https://x.com/pin/7", source="manual")
    pending = Job.create(
        source="manual",
        company="Stripe",
        title="Eng",
        url="https://x.com/pin/8",
        score=None,
        status="needs_review",
    )
    ScanLog.create(job_url="https://x.com/pin/8", source="manual")
    first = await add_job(
        "https://x.com/pin/7", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
    )
    second = await add_job(
        "https://x.com/pin/8", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
    )
    assert first == f"Job already in the database (id={scored.id}, score=7.2, status=new)."
    assert second == (
        f"Job already in the database (id={pending.id}, score=—, status=needs_review)."
        " Use verify_job(job_id, page_text) to score it from the real page."
    )
