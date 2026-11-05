"""A scan skips a job silently when its URL is already saved or claimed."""

from moonlighter.core.db import Job, ScanLog, init_db
from moonlighter.discovery.pipeline import evaluate_and_store
from moonlighter.discovery.sources.base import RawJob

from tests.discovery.scan_fakes import HOME_BH, make_raw_job, run_scan


async def test_scan_integrity_error_on_save_skips_silently(temporary_database):
    init_db()
    # Pre-creates a Job with the same URL (no entry in ScanLog) → the claim succeeds,
    # evaluates, but Job.create collides → IntegrityError → job is skipped (return None).
    Job.create(source="x", company="x", title="x", url="https://x.com/scan/5", status="new")
    result = await run_scan([make_raw_job(5)])
    assert "processed" in result
    assert "No new jobs found" not in result


async def test_scan_title_filtered_integrity_error_skips_silently(temporary_database):
    init_db()
    # Title in the blocklist + pre-existing Job (no ScanLog) → the filter branch
    # tenta Job.create archived, colide → IntegrityError → pulada (return None).
    Job.create(source="x", company="x", title="x", url="https://x.com/scan/6", status="new")
    result = await run_scan([make_raw_job(6, title="Staff Accountant")])
    assert "processed" in result
    assert "No new jobs found" not in result


async def test_scan_location_ineligible_integrity_error_skips_silently(temporary_database):
    init_db()
    # Ineligible location + pre-existing Job (no ScanLog) → the eligibility branch
    # attempts Job.create archived, collides → IntegrityError → skipped (return None).
    Job.create(source="x", company="x", title="x", url="https://x.com/scan/9", status="new")
    raw = RawJob(
        source="greenhouse",
        company="co",
        title="Engineer",
        url="https://x.com/scan/9",
        location="Bangalore, India",
        remote_type="onsite",
        description="A detailed job description that goes on.",
    )
    result = await run_scan([raw], profile=HOME_BH)
    assert "processed" in result
    assert "No new jobs found" not in result


async def test_scan_needs_review_integrity_error_skips_silently(temporary_database):
    init_db()
    # Insufficient description + pre-existing Job (no ScanLog) → the needs_review branch
    # attempts Job.create needs_review, collides → IntegrityError → skipped (return None).
    Job.create(source="x", company="x", title="x", url="https://x.com/scan/8", status="new")
    raw = RawJob(
        source="greenhouse",
        company="co",
        title="Engineer",
        url="https://x.com/scan/8",
        description=None,
    )
    result = await run_scan([raw])
    assert "processed" in result
    assert "No new jobs found" not in result


async def test_scan_chunk_skips_already_claimed_job(temporary_database):
    init_db()
    # Pre-inserts a claim for the URL → _claim returns False → job skipped without calling the LLM.
    ScanLog.create(job_url="https://x.com/scan/99", source="greenhouse")

    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        raise AssertionError("LLM must not be called for an already-claimed job")

    config = {
        "score_threshold": 6.5,
        "eval_model": "m",
        "scan_concurrency": 5,
        "scan_batch_size": 5,
        "title_blocklist": [],
    }
    saved, spend_hit = await evaluate_and_store([make_raw_job(99)], config, {}, caller=caller)
    assert saved == []
    assert spend_hit is False
    assert ScanLog.select().count() == 1  # only the pre-existing claim
