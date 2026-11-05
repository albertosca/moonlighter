"""A --no-eval scan costs no token: it parks what it would have scored."""

from unittest.mock import AsyncMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.scan.pipeline import evaluate_and_store
from moonlighter.discovery.screening.no_eval import NO_EVAL
from tests.discovery.scan_fakes import evaluation_result, make_raw_job, store_config


async def test_no_eval_persists_evaluable_jobs_as_needs_review_without_an_llm(temporary_database):
    # caller=NO_EVAL is the zero-LLM mode. A job that WOULD have gone to the
    # model is stored unscored for verify_job later; nothing else changes.
    init_db()
    raw = make_raw_job(1)  # a plain "Engineer" title with a description: evaluable
    saved, spend_hit = await evaluate_and_store(
        [raw],
        {
            "score_threshold": 6.5,
            "title_blocklist": [],
            "scan_concurrency": 2,
            "scan_batch_size": 5,
        },
        {},
        caller=NO_EVAL,
    )
    assert spend_hit is False
    assert [job.status for job in saved] == ["needs_review"]
    assert saved[0].score is None
    assert saved[0].score_notes == "not evaluated (--no-eval)"


async def test_no_eval_still_archives_title_filtered_jobs_deterministically(temporary_database):
    init_db()
    raw = make_raw_job(2, title="Recruiter")
    saved, _ = await evaluate_and_store(
        [raw],
        {
            "score_threshold": 6.5,
            "title_blocklist": ["recruiter"],
            "scan_concurrency": 2,
            "scan_batch_size": 5,
        },
        {},
        caller=NO_EVAL,
    )
    assert [job.status for job in saved] == ["archived"]
    assert saved[0].score_notes.startswith("title filtered:")


async def test_no_eval_needs_review_integrity_error_skips_silently(temporary_database):
    init_db()
    # Pre-existing Job at the same URL (no ScanLog claim) -> the --no-eval
    # branch's Job.create collides -> IntegrityError -> _persist returns None
    # -> skipped, same as every other persist site in this function.
    Job.create(source="x", company="x", title="x", url="https://x.com/scan/1", status="new")
    raw = make_raw_job(1)
    saved, spend_hit = await evaluate_and_store(
        [raw],
        {
            "score_threshold": 6.5,
            "title_blocklist": [],
            "scan_concurrency": 2,
            "scan_batch_size": 5,
        },
        {},
        caller=NO_EVAL,
    )
    assert saved == []
    assert spend_hit is False


async def test_a_stray_none_caller_does_not_take_the_no_eval_shortcut(temporary_database):
    # The hardening this guards: NO_EVAL is a dedicated sentinel, not None, so
    # an accidental caller=None elsewhere can never silently match it and skip
    # the LLM. Proven by mocking evaluate_jobs_batch and asserting it's called.
    init_db()
    raw = make_raw_job(1)
    batch = AsyncMock(return_value=[evaluation_result(8.0)])
    with patch("moonlighter.discovery.scan.pipeline.evaluate_jobs_batch", batch):
        await evaluate_and_store(
            [raw],
            {
                "score_threshold": 6.5,
                "title_blocklist": [],
                "scan_concurrency": 2,
                "scan_batch_size": 5,
            },
            {},
            caller=None,
        )
    batch.assert_awaited_once()


async def test_no_eval_parks_evaluable_jobs_after_the_filtered_ones_in_raw_order(
    temporary_database,
):
    init_db()
    jobs = [
        make_raw_job(1),
        make_raw_job(2, title="Recruiter"),
        make_raw_job(3),
        make_raw_job(4, title="Recruiter"),
    ]
    saved, _ = await evaluate_and_store(
        jobs, store_config(title_blocklist=["recruiter"]), {}, caller=NO_EVAL
    )
    assert [(job.company, job.status) for job in saved] == [
        ("Co2", "archived"),
        ("Co4", "archived"),
        ("Co1", "needs_review"),
        ("Co3", "needs_review"),
    ]
