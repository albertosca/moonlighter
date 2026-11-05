"""Tests for the results evaluate_job builds from well-formed replies."""

import json

from moonlighter.discovery.evaluation.models import EvaluationResult
from moonlighter.discovery.evaluation.single import evaluate_job
from tests.discovery.evaluation.evaluation_fakes import (
    JOB_DESCRIPTION,
    MOCK_LLM_RESPONSE,
    PROFILE,
    make_caller,
)


async def test_evaluate_job_returns_result():
    result = await evaluate_job(
        company="Acme",
        title="Sr Elixir Eng",
        description=JOB_DESCRIPTION,
        profile=PROFILE,
        model="claude-sonnet-4-6",
        _caller=make_caller(MOCK_LLM_RESPONSE),
        location=None,
        remote_type=None,
    )

    assert isinstance(result, EvaluationResult)
    assert result.score == 8.5
    assert result.salary_min == 180000
    assert "EST" in result.caveats[0]


async def test_evaluate_job_score_10():
    """Score of 10.0 is preserved exactly."""
    response = json.dumps(
        {
            "score": 10.0,
            "score_notes": "Perfect match.",
            "caveats": [],
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_source": None,
        }
    )
    result = await evaluate_job(
        company="Co",
        title="Eng",
        description="desc",
        profile=PROFILE,
        model="test",
        _caller=make_caller(response),
        location=None,
        remote_type=None,
    )
    assert result.score == 10.0


async def test_evaluate_job_partial_json_missing_salary():
    """JSON with no salary fields → salary_* all None."""
    response = json.dumps({"score": 7.0, "score_notes": "Good match.", "caveats": []})
    result = await evaluate_job(
        company="Co",
        title="Eng",
        description="desc",
        profile=PROFILE,
        model="test",
        _caller=make_caller(response),
        location=None,
        remote_type=None,
    )
    assert result.salary_min is None
    assert result.salary_max is None
    assert result.salary_currency is None
    assert result.salary_source is None


async def test_evaluate_job_caveats_empty_array():
    """Empty caveats array returns []."""
    response = json.dumps(
        {
            "score": 7.0,
            "score_notes": "Ok.",
            "caveats": [],
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_source": None,
        }
    )
    result = await evaluate_job(
        company="Co",
        title="Eng",
        description="desc",
        profile=PROFILE,
        model="test",
        _caller=make_caller(response),
        location=None,
        remote_type=None,
    )
    assert result.caveats == []


async def test_evaluate_job_caveats_multiple():
    """Multiple caveats are all preserved."""
    response = json.dumps(
        {
            "score": 5.0,
            "score_notes": "Mixed.",
            "caveats": ["US citizens only", "requires visa", "must relocate"],
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_source": None,
        }
    )
    result = await evaluate_job(
        company="Co",
        title="Eng",
        description="desc",
        profile=PROFILE,
        model="test",
        _caller=make_caller(response),
        location=None,
        remote_type=None,
    )
    assert len(result.caveats) == 3
    assert "US citizens only" in result.caveats


async def test_evaluate_job_salary_source_preserved():
    """salary_source from LLM response is preserved in result."""
    response = json.dumps(
        {
            "score": 8.0,
            "score_notes": "Great.",
            "caveats": [],
            "salary_min": 150000,
            "salary_max": 200000,
            "salary_currency": "USD",
            "salary_source": "stated",
        }
    )
    result = await evaluate_job(
        company="Co",
        title="Eng",
        description="desc",
        profile=PROFILE,
        model="test",
        _caller=make_caller(response),
        location=None,
        remote_type=None,
    )
    assert result.salary_source == "stated"
    assert result.salary_min == 150000
