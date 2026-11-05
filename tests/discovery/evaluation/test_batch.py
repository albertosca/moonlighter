"""Tests for evaluate_jobs_batch calls, prompts and spend-limit handling."""

from unittest.mock import patch

import pytest
from moonlighter.discovery.evaluation.batch import evaluate_jobs_batch
from moonlighter.discovery.evaluation.models import EvalInput

from tests.discovery.evaluation.evaluation_fakes import (
    SPEND_LIMIT_MESSAGE,
    inputs,
    recording_caller,
)


async def test_batch_happy_path_single_call():
    calls = {"n": 0}

    async def caller(prompt, model, cache_prefix=None):
        calls["n"] += 1
        return '[{"score": 8.0, "score_notes": "a", "caveats": []}, {"score": 2.0, "score_notes": "b", "caveats": []}]'

    results = await evaluate_jobs_batch(inputs(2), {}, "m", caller=caller)
    assert [result.score for result in results] == [8.0, 2.0]
    assert calls["n"] == 1  # a single call for the batch


async def test_batch_spend_limit_propagates():
    async def caller(prompt, model, cache_prefix=None):
        raise RuntimeError("spend limit reached")

    with pytest.raises(RuntimeError, match="spend limit"):
        await evaluate_jobs_batch(inputs(2), {}, "m", caller=caller)


async def test_a_spend_limit_in_the_batch_call_is_recorded_before_it_propagates():
    async def caller(prompt, model, cache_prefix=None):
        raise RuntimeError(SPEND_LIMIT_MESSAGE)

    with (
        patch("moonlighter.discovery.evaluation.batch.record_spend_limit_hit") as record,
        pytest.raises(RuntimeError, match="spend limit"),
    ):
        await evaluate_jobs_batch(inputs(2), {}, "m", caller=caller)
    record.assert_called_once_with()


async def test_an_ordinary_error_in_the_batch_call_records_no_spend_limit_hit():
    async def caller(prompt, model, cache_prefix=None):
        raise RuntimeError("boom")

    with patch("moonlighter.discovery.evaluation.batch.record_spend_limit_hit") as record:
        await evaluate_jobs_batch(inputs(2), {}, "m", caller=caller)
    record.assert_not_called()


async def test_a_batch_of_no_jobs_still_asks_the_model_once():
    caller, calls = recording_caller("[]")
    assert await evaluate_jobs_batch([], {}, "m", caller=caller) == []
    assert len(calls) == 1
    assert "exactly 0 objects" in calls[0][2]


async def test_a_batch_reply_that_is_not_text_propagates_instead_of_falling_back():
    async def caller(prompt, model, cache_prefix=None):
        return None

    with pytest.raises(TypeError):
        await evaluate_jobs_batch(inputs(2), {}, "m", caller=caller)


async def test_the_batch_prompt_carries_each_jobs_location_and_remote_type():
    # Route of the 2026-08-21 GitLab false positives: no other test saw the batch lines.
    jobs = [
        EvalInput("Acme", "Eng", "d0", "Bangalore, India", "remote"),
        EvalInput("Beta", "Dev", "d1"),
    ]
    caller, calls = recording_caller('[{"score": 1.0}, {"score": 2.0}]')
    await evaluate_jobs_batch(jobs, {}, "m", caller=caller)
    prompt = calls[0][0]
    assert (
        "Company: Acme\nTitle: Eng\nLocation: Bangalore, India\nRemote type: remote\nDescription:\nd0"
        in prompt
    )
    assert "Company: Beta\nTitle: Dev\nDescription:\nd1" in prompt
    assert prompt.count("Location:") == 1
    assert prompt.count("Remote type:") == 1


async def test_each_batch_posting_is_capped_at_8000_characters():
    job = EvalInput("Co", "Eng", "x" * 10000)
    caller, calls = recording_caller('[{"score": 1.0}, {"score": 2.0}]')
    await evaluate_jobs_batch([job, EvalInput("Co", "Dev", "d")], {}, "m", caller=caller)
    assert "x" * 8001 not in calls[0][0]
    assert "x" * 7964 in calls[0][0]
