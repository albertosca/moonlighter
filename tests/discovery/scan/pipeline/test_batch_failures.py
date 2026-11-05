"""A scan stops conservatively on a spend limit or an unexpected batch error."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import ScanLog, init_db
from moonlighter.discovery.scan.pipeline import evaluate_and_store
from tests.discovery.fake_scan import make_raw_job, run_scan, store_config


async def test_scan_stops_before_llm_after_spend_limit(temporary_database):
    init_db()
    calls = {"n": 0}

    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        calls["n"] += 1
        raise RuntimeError("spend limit reached")

    config = {
        "score_threshold": 6.5,
        "eval_model": "m",
        "scan_concurrency": 1,
        "scan_batch_size": 1,
        "title_blocklist": [],
    }
    jobs = [make_raw_job(index) for index in range(5)]
    _saved, spend_hit = await evaluate_and_store(jobs, config, {}, caller=caller)
    assert spend_hit is True
    # concurrency=1: the 1st call detects the spend-limit and sets stop; the rest see
    # stop=True right after the semaphore and don't even call the LLM.
    assert calls["n"] == 1
    assert ScanLog.select().count() == 0  # all claims released


async def test_scan_unexpected_eval_error_stops_conservatively(temporary_database):
    init_db()
    result = await run_scan(
        [make_raw_job(4)], eval_mock=AsyncMock(side_effect=ValueError("unexpected error"))
    )
    # a non-spend error is logged and propagated; the scan stops conservatively and
    # the ScanLog claim is released (no orphan) for a future retry.
    assert ScanLog.select().count() == 0
    assert "processed" in result
    assert "No new jobs found" not in result


async def test_unexpected_batch_error_keeps_the_chunk_results_and_logs_with_traceback(
    temporary_database, caplog
):
    init_db()
    batch = AsyncMock(side_effect=ValueError("unexpected error"))
    with patch("moonlighter.discovery.scan.pipeline.evaluate_jobs_batch", new=batch):
        saved, spend_hit = await evaluate_and_store(
            [make_raw_job(1), make_raw_job(2, title="Recruiter")],
            store_config(title_blocklist=["recruiter"]),
            {},
            caller=MagicMock(),
        )
    assert spend_hit is True
    assert [job.company for job in saved] == ["Co2"]
    assert [row.job_url for row in ScanLog.select()] == ["https://x.com/scan/2"]
    records = [record for record in caplog.records if "unexpected error in batch" in record.message]
    assert [(record.levelno, record.getMessage()) for record in records] == [
        (logging.ERROR, "scan: unexpected error in batch — unexpected error")
    ]
    assert records[0].exc_info is not None
    assert records[0].exc_info[0] is ValueError


async def test_a_batch_that_returns_too_few_results_is_reported_as_failed(
    temporary_database, caplog
):
    init_db()
    batch = AsyncMock(return_value=[])
    with patch("moonlighter.discovery.scan.pipeline.evaluate_jobs_batch", new=batch):
        saved, spend_hit = await evaluate_and_store(
            [make_raw_job(1)], store_config(), {}, caller=MagicMock()
        )
    assert saved == []
    assert spend_hit is True
    records = [record for record in caplog.records if "batch failed" in record.message]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].getMessage().startswith("scan: batch failed — zip() argument 2 is shorter")
    assert records[0].exc_info is None


async def test_spend_limit_keeps_the_filtered_jobs_and_logs_the_warning(temporary_database, caplog):
    init_db()

    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        raise RuntimeError("spend limit reached")

    saved, spend_hit = await evaluate_and_store(
        [make_raw_job(1), make_raw_job(2, title="Recruiter")],
        store_config(title_blocklist=["recruiter"], eval_model="m"),
        {},
        caller=caller,
    )
    assert spend_hit is True
    assert [job.company for job in saved] == ["Co2"]
    records = [record for record in caplog.records if "stopped by spend limit" in record.message]
    assert [(record.levelno, record.getMessage()) for record in records] == [
        (logging.WARNING, "scan_and_evaluate: stopped by spend limit after 1 jobs")
    ]
