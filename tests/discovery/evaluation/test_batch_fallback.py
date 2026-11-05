"""Tests for the per-job fallback evaluate_jobs_batch takes when a batch fails."""

import asyncio
import logging

from moonlighter.discovery.evaluation.batch import evaluate_jobs_batch
from moonlighter.discovery.evaluation.models import EvalInput
from tests.discovery.evaluation.evaluation_fakes import (
    MOCK_LLM_RESPONSE,
    inputs,
    recording_caller,
    warning_records,
)


async def test_batch_falls_back_per_job_on_bad_json():
    calls = {"n": 0}

    async def caller(prompt, model, cache_prefix=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return "garbage not json"  # batch fails to parse
        return '{"score": 5.0, "score_notes": "x", "caveats": []}'  # per-job

    results = await evaluate_jobs_batch(inputs(2), {}, "m", caller=caller)
    assert [result.score for result in results] == [5.0, 5.0]
    assert calls["n"] == 3  # 1 batch (failed) + 2 per-job


async def test_batch_single_job_uses_single_path():
    calls = {"n": 0}

    async def caller(prompt, model, cache_prefix=None):
        calls["n"] += 1
        return '{"score": 7.0, "score_notes": "x", "caveats": []}'

    results = await evaluate_jobs_batch(inputs(1), {}, "m", caller=caller)
    assert results[0].score == 7.0
    assert calls["n"] == 1


async def test_batch_falls_back_per_job_on_non_spend_error():
    """Non-spend error in the batch call → per-job fallback (score=0 via evaluate_job)."""
    calls = {"n": 0}

    async def caller(prompt, model, cache_prefix=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("timeout")  # non-spend error: fallback
        return '{"score": 3.0, "score_notes": "y", "caveats": []}'

    results = await evaluate_jobs_batch(inputs(2), {}, "m", caller=caller)
    assert calls["n"] == 3  # 1 batch (error) + 2 per-job
    assert len(results) == 2
    assert [result.score for result in results] == [3.0, 3.0]


async def test_a_failed_batch_call_is_logged_with_the_traceback_before_the_fallback(caplog):
    async def caller(prompt, model, cache_prefix=None):
        raise RuntimeError("boom")

    with caplog.at_level(logging.DEBUG):
        await evaluate_jobs_batch(inputs(2), {}, "m", caller=caller)
    record = warning_records(caplog)[0]
    assert record.getMessage() == "batch eval: call error — fallback per-job: boom"
    assert record.exc_info is not None


async def test_an_invalid_batch_reply_is_logged_without_a_traceback_before_the_fallback(caplog):
    caller, _ = recording_caller("garbage", MOCK_LLM_RESPONSE)
    with caplog.at_level(logging.DEBUG):
        await evaluate_jobs_batch(inputs(2), {}, "m", caller=caller)
    (record,) = warning_records(caplog)
    assert record.getMessage() == "batch eval: invalid parse — fallback per-job (2 jobs)"
    assert record.exc_info is None


async def test_a_batch_of_one_job_forwards_its_location_to_the_single_prompt():
    caller, calls = recording_caller('{"score": 1.0}')
    await evaluate_jobs_batch(
        [EvalInput("Acme", "Eng", "d0", "Italy", "hybrid")], {}, "m", caller=caller
    )
    assert "Location: Italy\nRemote type: hybrid\nDescription:\nd0" in calls[0][0]


async def test_the_per_job_fallback_forwards_the_model_and_each_jobs_location():
    jobs = [
        EvalInput("Acme", "Eng", "d0", "Bangalore, India", "remote"),
        EvalInput("Beta", "Dev", "d1"),
    ]
    caller, calls = recording_caller("garbage", '{"score": 5.0}')
    await evaluate_jobs_batch(jobs, {}, "model-x", caller=caller)
    assert [model for _, model, _ in calls] == ["model-x", "model-x", "model-x"]
    assert "Company: Acme" in calls[1][0]
    assert "Location: Bangalore, India\nRemote type: remote" in calls[1][0]
    assert "Company: Beta" in calls[2][0]
    assert "Location:" not in calls[2][0]


async def test_the_per_job_fallback_runs_one_job_at_a_time_in_order():
    log = []
    calls = {"count": 0}

    async def caller(prompt, model, cache_prefix=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return "garbage"
        label = "Co0" if "Company: Co0" in prompt else "Co1"
        log.append(f"start {label}")
        await asyncio.sleep(0)
        log.append(f"end {label}")
        return '{"score": 5.0}'

    await evaluate_jobs_batch(inputs(2), {}, "m", caller=caller)
    assert log == ["start Co0", "end Co0", "start Co1", "end Co1"]
