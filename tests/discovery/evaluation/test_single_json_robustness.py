"""Tests for replies wrapped in prose or carrying malformed score and caveat fields."""

import json

from moonlighter.discovery.evaluation.single import evaluate_job

from tests.discovery.evaluation.evaluation_fakes import JOB_DESCRIPTION, PROFILE, make_caller


async def test_evaluate_job_strips_markdown_fence():
    """LLM returns JSON inside ```json ... ``` → parsed correctly, valid score."""
    payload = {
        "score": 7.5,
        "score_notes": "Good.",
        "caveats": [],
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "salary_source": None,
    }
    wrapped = f"```json\n{json.dumps(payload)}\n```"
    result = await evaluate_job(
        company="Co",
        title="Eng",
        description="desc",
        profile=PROFILE,
        model="test",
        _caller=make_caller(wrapped),
        location=None,
        remote_type=None,
    )
    assert result.score == 7.5


async def test_evaluate_job_strips_markdown_fence_without_json_label():
    """LLM returns JSON inside ``` ... ``` (with no 'json' label) → parsed correctly."""
    payload = {
        "score": 6.0,
        "score_notes": "Ok.",
        "caveats": [],
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "salary_source": None,
    }
    wrapped = f"```\n{json.dumps(payload)}\n```"
    result = await evaluate_job(
        company="Co",
        title="Eng",
        description="desc",
        profile=PROFILE,
        model="test",
        _caller=make_caller(wrapped),
        location=None,
        remote_type=None,
    )
    assert result.score == 6.0


async def test_evaluate_job_strips_leading_prose():
    """LLM returns introductory text followed by JSON → JSON extracted and parsed."""
    payload = {
        "score": 8.0,
        "score_notes": "Great.",
        "caveats": [],
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "salary_source": None,
    }
    with_prose = f"Here is my evaluation:\n\n{json.dumps(payload)}"
    result = await evaluate_job(
        company="Co",
        title="Eng",
        description="desc",
        profile=PROFILE,
        model="test",
        _caller=make_caller(with_prose),
        location=None,
        remote_type=None,
    )
    assert result.score == 8.0


async def test_evaluate_job_null_score_becomes_zero_keeps_notes():
    """A null score → 0.0 while preserving the notes (doesn't fall into 'evaluation error')."""
    caller = make_caller(json.dumps({"score": None, "score_notes": "no score", "caveats": ["x"]}))
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
    assert result.score_notes == "no score"
    assert result.caveats == ["x"]


async def test_evaluate_job_non_numeric_score_becomes_zero():
    caller = make_caller(json.dumps({"score": "high", "score_notes": "n"}))
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


async def test_evaluate_job_non_list_caveats_becomes_empty():
    caller = make_caller(json.dumps({"score": 7.0, "caveats": "not a list"}))
    result = await evaluate_job(
        company="C",
        title="T",
        description=JOB_DESCRIPTION,
        profile=PROFILE,
        _caller=caller,
        location=None,
        remote_type=None,
    )
    assert result.caveats == []
