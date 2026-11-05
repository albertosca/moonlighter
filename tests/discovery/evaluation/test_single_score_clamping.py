"""Tests for clamping the score evaluate_job reads from a reply."""

import json

from moonlighter.discovery.evaluation.single import evaluate_job
from tests.discovery.evaluation.fake_evaluation import JOB_DESCRIPTION, PROFILE, make_caller


async def test_evaluate_job_score_above_10_is_clamped():
    """A score above the valid range is clamped to 10.0, never trusted verbatim."""
    caller = make_caller(json.dumps({"score": 99, "score_notes": "n", "caveats": []}))
    result = await evaluate_job(
        company="C",
        title="T",
        description=JOB_DESCRIPTION,
        profile=PROFILE,
        _caller=caller,
        location=None,
        remote_type=None,
    )
    assert result.score == 10.0


async def test_evaluate_job_negative_score_is_clamped():
    caller = make_caller(json.dumps({"score": -5, "score_notes": "n", "caveats": []}))
    result = await evaluate_job(
        company="C",
        title="T",
        description=JOB_DESCRIPTION,
        profile=PROFILE,
        _caller=caller,
        location=None,
        remote_type=None,
    )
    assert result.score == 0.0


async def test_evaluate_job_infinite_score_becomes_zero():
    """A string LLM output like "Infinity" parses via float() to inf — must be rejected."""
    caller = make_caller(json.dumps({"score": "Infinity", "score_notes": "n", "caveats": []}))
    result = await evaluate_job(
        company="C",
        title="T",
        description=JOB_DESCRIPTION,
        profile=PROFILE,
        _caller=caller,
        location=None,
        remote_type=None,
    )
    assert result.score == 0.0


async def test_evaluate_job_nan_score_becomes_zero():
    caller = make_caller(json.dumps({"score": "NaN", "score_notes": "n", "caveats": []}))
    result = await evaluate_job(
        company="C",
        title="T",
        description=JOB_DESCRIPTION,
        profile=PROFILE,
        _caller=caller,
        location=None,
        remote_type=None,
    )
    assert result.score == 0.0
