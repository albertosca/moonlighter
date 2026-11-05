"""verify_job re-scores a pending job from the page text a person pasted."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.manual.jobs import verify_job
from moonlighter.discovery.sources.base import RawJob
from tests.discovery.scan_fakes import CONFIG, PROFILE, evaluation_result, run_scan


async def test_verify_job_not_found_returns_message(temporary_database):
    init_db()
    result = await verify_job(
        999, "some page text here", CONFIG, profile=PROFILE, caller=MagicMock()
    )
    assert "not found" in result.lower()


async def test_verify_job_rejects_a_job_not_pending_verification(temporary_database):
    init_db()
    job = Job.create(
        source="manual",
        company="Acme",
        title="Eng",
        url="https://x.com/vj/1",
        status="new",
        score=8.0,
    )
    result = await verify_job(job.id, "text", CONFIG, profile=PROFILE, caller=MagicMock())
    assert "not pending verification" in result
    assert "new" in result


async def test_verify_job_rejects_a_too_short_paste_and_leaves_job_pending(temporary_database):
    init_db()
    job = Job.create(
        source="inhire",
        company="Alice",
        title="Squad Manager",
        url="https://alice.inhire.app/vagas/9",
        status="needs_review",
        score=None,
    )
    eval_mock = AsyncMock(return_value=evaluation_result(8.0))
    with patch("moonlighter.discovery.manual.jobs.evaluate_job", new=eval_mock):
        result = await verify_job(job.id, "  ", CONFIG, profile=PROFILE, caller=MagicMock())
    eval_mock.assert_not_called()
    assert "too short" in result
    assert "0 chars" in result
    assert "stays pending" in result
    assert Job.get_by_id(job.id).status == "needs_review"


async def test_verify_job_hands_the_stored_location_to_the_evaluator(temporary_database):
    init_db()
    job = Job.create(
        source="greenhouse",
        company="GitLab",
        title="Engineer",
        url="https://x.com/vj/location",
        location="Bangalore, India",
        remote_type="onsite",
        status="needs_review",
        score=None,
    )
    eval_mock = AsyncMock(return_value=evaluation_result(8.0))
    with patch("moonlighter.discovery.manual.jobs.evaluate_job", new=eval_mock):
        await verify_job(
            job.id,
            "Full page text with the real job description.",
            CONFIG,
            profile=PROFILE,
            caller=MagicMock(),
        )
    assert eval_mock.call_args.kwargs["location"] == "Bangalore, India"
    assert eval_mock.call_args.kwargs["remote_type"] == "onsite"


async def test_verify_job_updates_the_same_row_and_scores_above_threshold(temporary_database):
    init_db()
    job = Job.create(
        source="inhire",
        company="Alice",
        title="Squad Manager",
        url="https://alice.inhire.app/vagas/1",
        status="needs_review",
        score=None,
        score_notes="description unavailable — needs manual verification",
    )
    with patch(
        "moonlighter.discovery.manual.jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(8.0)),
    ):
        result = await verify_job(
            job.id,
            "Full page text with the real job description.",
            CONFIG,
            profile=PROFILE,
            caller=MagicMock(),
        )
    refreshed = Job.get_by_id(job.id)
    assert refreshed.status == "new"
    assert refreshed.score == 8.0
    assert refreshed.description == "Full page text with the real job description."
    assert Job.select().where(Job.url == job.url).count() == 1
    assert "NEW" in result
    assert "Alice" in result


async def test_verify_job_scores_a_row_that_scan_actually_produced(temporary_database):
    """Crosses the scan -> verify_job seam: builds the needs_review row through the
    real scan pipeline, then scores it through verify_job -- proving the two sides
    agree on the row's shape (e.g. caveats='[]'), not just that each works against
    a hand-built Job in isolation.
    """
    init_db()
    raw = RawJob(
        source="greenhouse",
        company="co",
        title="Engineer",
        url="https://x.com/scan/seam",
        description=None,
    )
    await run_scan([raw])
    job = Job.get(Job.url == "https://x.com/scan/seam")
    assert job.status == "needs_review"
    assert job.caveats == "[]"

    with patch(
        "moonlighter.discovery.manual.jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(8.0)),
    ):
        result = await verify_job(
            job.id,
            "Full page text with the real job description.",
            CONFIG,
            profile=PROFILE,
            caller=MagicMock(),
        )
    refreshed = Job.get_by_id(job.id)
    assert refreshed.status == "new"
    assert refreshed.description == "Full page text with the real job description."
    assert "NEW" in result


async def test_verify_job_below_threshold_archives(temporary_database):
    init_db()
    job = Job.create(
        source="inhire",
        company="Infleet",
        title="Elixir Engineer",
        url="https://infleet.inhire.app/vagas/1",
        status="needs_review",
        score=None,
    )
    with patch(
        "moonlighter.discovery.manual.jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(3.0)),
    ):
        result = await verify_job(
            job.id,
            "Full page text with the real job description.",
            CONFIG,
            profile=PROFILE,
            caller=MagicMock(),
        )
    refreshed = Job.get_by_id(job.id)
    assert refreshed.status == "archived"
    assert "archived" in result
