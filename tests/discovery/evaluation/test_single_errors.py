"""Tests for how evaluate_job reports failed calls and unusable replies."""

from unittest.mock import patch

import pytest

from moonlighter.discovery.evaluation.models import EvaluationResult
from moonlighter.discovery.evaluation.single import evaluate_job
from tests.discovery.evaluation.fake_evaluation import (
    MOCK_LLM_RESPONSE,
    PROFILE,
    SPEND_LIMIT_MESSAGE,
    evaluate_once,
    make_caller,
    recording_caller,
)


async def test_evaluate_job_handles_malformed_json():
    result = await evaluate_job(
        company="Acme",
        title="Eng",
        description="desc",
        profile=PROFILE,
        model="claude-sonnet-4-6",
        _caller=make_caller("not json"),
        location=None,
        remote_type=None,
    )

    assert result.score == 0.0
    assert "parse error" in result.score_notes.lower()


async def test_evaluate_job_llm_exception_returns_zero():
    """Any exception from caller → score=0.0 with 'evaluation error' in notes."""

    async def failing_caller(prompt, model, cache_prefix=None):
        raise Exception("network timeout")  # noqa: TRY002 - a plain Exception is what an SDK failure looks like

    result = await evaluate_job(
        company="Co",
        title="Eng",
        description="desc",
        profile=PROFILE,
        model="test",
        _caller=failing_caller,
        location=None,
        remote_type=None,
    )
    assert result.score == 0.0
    assert "evaluation error" in result.score_notes.lower()


async def test_evaluate_job_spend_limit_propagates():
    """Spend limit error must propagate — caller must not swallow it."""

    async def spend_limit_caller(prompt, model, cache_prefix=None):
        raise Exception(  # noqa: TRY002 - a plain Exception is what an SDK failure looks like
            "You've hit your monthly spend limit · raise it at claude.ai/settings/usage"
        )

    with pytest.raises(Exception, match="spend limit"):
        await evaluate_job(
            company="Co",
            title="Eng",
            description="desc",
            profile=PROFILE,
            model="test",
            _caller=spend_limit_caller,
            location=None,
            remote_type=None,
        )


async def test_evaluate_job_rate_limit_propagates():
    """Rate limit / quota errors must also propagate."""

    async def quota_caller(prompt, model, cache_prefix=None):
        raise Exception("429 Too Many Requests: quota exceeded")  # noqa: TRY002 - a plain Exception is what an SDK failure looks like

    with pytest.raises(Exception, match="429"):
        await evaluate_job(
            company="Co",
            title="Eng",
            description="desc",
            profile=PROFILE,
            model="test",
            _caller=quota_caller,
            location=None,
            remote_type=None,
        )


async def test_evaluate_job_session_limit_propagates():
    """Claude CLI's real 'session limit' message must also propagate — it's a
    spend-limit variant, not a per-job error. Regression: is_spend_limit() didn't
    recognize this phrase, so callers never stopped early on it.
    """

    async def session_limit_caller(prompt, model, cache_prefix=None):
        raise Exception("You've hit your session limit · resets 12:40am (America/Sao_Paulo)")  # noqa: TRY002 - a plain Exception is what an SDK failure looks like

    with pytest.raises(Exception, match="session limit"):
        await evaluate_job(
            company="Co",
            title="Eng",
            description="desc",
            profile=PROFILE,
            model="test",
            _caller=session_limit_caller,
            location=None,
            remote_type=None,
        )


async def test_evaluate_job_requires_location_and_remote_type_by_name():
    """Optional defaults let an ad-hoc caller drop them silently (2026-09-25 re-eval:
    4 of 6 promoted jobs were false positives). A caller must now say None on purpose.
    """

    async def caller(prompt, model, cache_prefix=None):
        return '{"score": 5.0, "score_notes": "x", "caveats": []}'

    with pytest.raises(TypeError, match="location"):
        await evaluate_job("Co", "Eng", "desc", {}, "m", caller)


async def test_a_reply_that_is_not_json_is_stored_with_this_exact_note():
    result = await evaluate_once(make_caller("not json"))
    assert result == EvaluationResult(score=0.0, score_notes="parse error: LLM returned non-JSON")


async def test_a_failed_call_is_stored_with_the_error_text_after_a_fixed_prefix():
    # scripts/build_blocklist.py and scripts/reevaluate_bug_victims.py find these rows by this prefix.
    async def failing_caller(prompt, model, cache_prefix=None):
        raise RuntimeError("claude CLI exited with code 1")

    result = await evaluate_once(failing_caller)
    assert result == EvaluationResult(
        score=0.0, score_notes="evaluation error: claude CLI exited with code 1"
    )


async def test_a_reply_that_is_json_but_not_an_object_is_an_evaluation_error():
    # _result_from runs inside the try, so the AttributeError becomes a stored result.
    result = await evaluate_once(make_caller("[]"))
    assert result.score == 0.0
    assert result.score_notes == "evaluation error: 'list' object has no attribute 'get'"


async def test_building_the_prompt_is_outside_the_try_so_its_errors_propagate():
    caller, calls = recording_caller(MOCK_LLM_RESPONSE)
    with pytest.raises(TypeError):
        await evaluate_job(
            company="Co",
            title="Eng",
            description="desc",
            profile=None,
            _caller=caller,
            location=None,
            remote_type=None,
        )
    assert calls == []


async def test_a_spend_limit_in_evaluate_job_is_recorded_before_it_propagates():
    async def caller(prompt, model, cache_prefix=None):
        raise RuntimeError(SPEND_LIMIT_MESSAGE)

    with (
        patch("moonlighter.discovery.evaluation.single.record_spend_limit_hit") as record,
        pytest.raises(RuntimeError, match="spend limit"),
    ):
        await evaluate_once(caller)
    record.assert_called_once_with()


async def test_an_ordinary_error_in_evaluate_job_records_no_spend_limit_hit():
    async def caller(prompt, model, cache_prefix=None):
        raise RuntimeError("boom")

    with patch("moonlighter.discovery.evaluation.single.record_spend_limit_hit") as record:
        await evaluate_once(caller)
    record.assert_not_called()
