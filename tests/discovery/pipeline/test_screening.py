"""A scan archives or parks what free checks can decide, without calling the LLM."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.pipeline import evaluate_and_store
from moonlighter.discovery.sources.base import RawJob

from tests.discovery.scan_fakes import (
    HOME_BH,
    BatchRecorder,
    evaluation_result,
    make_raw_job,
    run_scan,
    store_config,
)


async def test_scan_title_filtered_archives_with_score_zero(temporary_database):
    init_db()
    result = await run_scan([make_raw_job(1, title="Staff Accountant")])
    job = Job.get(Job.url == "https://x.com/scan/1")
    assert job.status == "archived"
    assert job.score == 0.0
    assert "title filtered" in job.score_notes
    assert "filtered by title" in result.lower()


async def test_scan_ineligible_location_archives_without_llm(temporary_database):
    # Live 2026-08-20/21: "Bangalore, India" passed at 8.5 because the
    # eligibility rule lived in the prompt and the LLM never saw the location
    # field. Onsite/hybrid outside Belo Horizonte is impossible regardless of
    # the JD — archived deterministically, no LLM call.
    init_db()
    raw = RawJob(
        source="greenhouse",
        company="Abroad Co",
        title="Engineer",
        url="https://x.com/scan/abroad",
        location="Bangalore, India",
        remote_type="onsite",
        description="A detailed job description that goes on.",
    )
    boom = AsyncMock(side_effect=AssertionError("LLM must not run for ineligible locations"))
    result = await run_scan([raw], eval_mock=boom, profile=HOME_BH)
    job = Job.get(Job.url == "https://x.com/scan/abroad")
    assert job.status == "archived"
    assert job.score == 0.0
    assert "location ineligible" in job.score_notes
    assert "location ineligible" in result.lower()


async def test_scan_without_a_home_city_never_archives_by_location(temporary_database):
    # A profile with no criteria.home_city (every public user by default):
    # onsite abroad is not impossible for them, so the LLM decides.
    init_db()
    raw = RawJob(
        source="greenhouse",
        company="Abroad Co",
        title="Engineer",
        url="https://x.com/scan/abroad-no-home",
        location="Bangalore, India",
        remote_type="onsite",
        description="A detailed job description that goes on.",
    )
    await run_scan([raw])
    job = Job.get(Job.url == "https://x.com/scan/abroad-no-home")
    assert "location ineligible" not in (job.score_notes or "")
    assert job.score == 8.0


async def test_scan_ambiguous_location_still_reaches_the_llm(temporary_database):
    # The documented Colombia case: the field names a country, the JD may say
    # "remote from anywhere in LATAM" — only the evaluator can read the JD.
    init_db()
    raw = RawJob(
        source="greenhouse",
        company="Andes Co",
        title="Engineer",
        url="https://x.com/scan/andes",
        location="Colombia",
        remote_type="remote",
        description="A detailed job description that goes on.",
    )
    await run_scan([raw])
    assert Job.get(Job.url == "https://x.com/scan/andes").status == "new"


async def test_scan_empty_description_skips_llm_and_needs_review(temporary_database):
    init_db()
    eval_mock = AsyncMock(return_value=evaluation_result(8.0))
    raw = RawJob(
        source="greenhouse",
        company="co",
        title="Engineer",
        url="https://x.com/scan/10",
        description=None,
    )
    result = await run_scan([raw], eval_mock=eval_mock)
    job = Job.get(Job.url == "https://x.com/scan/10")
    assert job.status == "needs_review"
    assert job.score is None
    assert job.score_notes == "description unavailable — needs manual verification"
    eval_mock.assert_not_called()
    assert "need manual verification" in result


async def test_scan_short_description_also_needs_review(temporary_database):
    init_db()
    raw = RawJob(
        source="greenhouse",
        company="co",
        title="Squad Manager",
        url="https://x.com/scan/11",
        description="too short",
    )
    result = await run_scan([raw])
    job = Job.get(Job.url == "https://x.com/scan/11")
    assert job.status == "needs_review"
    assert "need manual verification" in result


async def test_scan_real_description_still_evaluates_normally(temporary_database):
    init_db()
    eval_mock = AsyncMock(return_value=evaluation_result(8.0))
    result = await run_scan([make_raw_job(12)], eval_mock=eval_mock)
    job = Job.get(Job.url == "https://x.com/scan/12")
    assert job.status == "new"
    assert job.score == 8.0
    eval_mock.assert_called_once()
    assert "need manual verification" not in result


async def test_chunk_persists_filtered_jobs_before_evaluated_ones_in_raw_order(
    temporary_database,
):
    init_db()
    jobs = [
        make_raw_job(1),
        make_raw_job(2, title="Recruiter"),
        make_raw_job(3),
        make_raw_job(4, title="Recruiter"),
    ]
    recorder = BatchRecorder()
    with patch("moonlighter.discovery.pipeline.evaluate_jobs_batch", new=recorder):
        saved, spend_hit = await evaluate_and_store(
            jobs, store_config(title_blocklist=["recruiter"]), {}, caller=MagicMock()
        )
    assert spend_hit is False
    assert recorder.sizes == [2]
    assert [job.company for job in saved] == ["Co2", "Co4", "Co1", "Co3"]
