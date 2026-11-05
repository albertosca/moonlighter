"""Tests for the salary source and currency evaluate_job accepts from a reply."""

import json

from moonlighter.discovery.evaluation.single import evaluate_job
from tests.discovery.evaluation.evaluation_fakes import JOB_DESCRIPTION, PROFILE, make_caller


async def test_evaluate_job_invalid_salary_source_becomes_none():
    caller = make_caller(
        json.dumps(
            {
                "score": 7.0,
                "score_notes": "x",
                "caveats": [],
                "salary_min": None,
                "salary_max": None,
                "salary_currency": None,
                "salary_source": "definitely_made_up",
            }
        )
    )
    result = await evaluate_job(
        company="C",
        title="T",
        description=JOB_DESCRIPTION,
        profile=PROFILE,
        _caller=caller,
        location=None,
        remote_type=None,
    )
    assert result.salary_source is None


async def test_evaluate_job_non_hashable_salary_source_becomes_none():
    """S-05: a non-string (unhashable) salary_source from the LLM must not crash
    the validator — it becomes None like any other invalid value, never raises.
    """
    caller = make_caller(
        json.dumps(
            {
                "score": 7.0,
                "score_notes": "x",
                "caveats": [],
                "salary_min": None,
                "salary_max": None,
                "salary_currency": None,
                "salary_source": ["stated"],
            }
        )
    )
    result = await evaluate_job(
        company="C",
        title="T",
        description=JOB_DESCRIPTION,
        profile=PROFILE,
        _caller=caller,
        location=None,
        remote_type=None,
    )
    assert result.salary_source is None


async def test_evaluate_job_overlong_salary_currency_is_truncated():
    caller = make_caller(
        json.dumps(
            {
                "score": 7.0,
                "score_notes": "x",
                "caveats": [],
                "salary_min": None,
                "salary_max": None,
                "salary_currency": "USD (estimated, converted from EUR at today's rate)",
                "salary_source": None,
            }
        )
    )
    result = await evaluate_job(
        company="C",
        title="T",
        description=JOB_DESCRIPTION,
        profile=PROFILE,
        _caller=caller,
        location=None,
        remote_type=None,
    )
    assert result.salary_currency is not None
    assert len(result.salary_currency) <= 10


async def test_evaluate_job_blank_salary_currency_becomes_none():
    caller = make_caller(
        json.dumps(
            {
                "score": 7.0,
                "score_notes": "x",
                "caveats": [],
                "salary_min": None,
                "salary_max": None,
                "salary_currency": "   ",
                "salary_source": None,
            }
        )
    )
    result = await evaluate_job(
        company="C",
        title="T",
        description=JOB_DESCRIPTION,
        profile=PROFILE,
        _caller=caller,
        location=None,
        remote_type=None,
    )
    assert result.salary_currency is None
