"""Tests for the salary amounts evaluate_job accepts from a reply."""

import json

from moonlighter.discovery.evaluation.single import evaluate_job

from tests.discovery.evaluation.evaluation_fakes import JOB_DESCRIPTION, PROFILE, make_caller


async def test_evaluate_job_negative_salary_becomes_none():
    caller = make_caller(
        json.dumps(
            {
                "score": 7.0,
                "score_notes": "x",
                "caveats": [],
                "salary_min": -100,
                "salary_max": None,
                "salary_currency": None,
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
    assert result.salary_min is None


async def test_evaluate_job_non_integer_salary_becomes_none():
    caller = make_caller(
        json.dumps(
            {
                "score": 7.0,
                "score_notes": "x",
                "caveats": [],
                "salary_min": "a lot of money",
                "salary_max": None,
                "salary_currency": None,
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
    assert result.salary_min is None


async def test_evaluate_job_bool_salary_becomes_none():
    """bool is an int subclass in Python — must be explicitly rejected."""
    caller = make_caller(
        json.dumps(
            {
                "score": 7.0,
                "score_notes": "x",
                "caveats": [],
                "salary_min": True,
                "salary_max": None,
                "salary_currency": None,
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
    assert result.salary_min is None


async def test_evaluate_job_float_salary_with_integer_value_is_accepted():
    caller = make_caller(
        json.dumps(
            {
                "score": 7.0,
                "score_notes": "x",
                "caveats": [],
                "salary_min": 150000.0,
                "salary_max": None,
                "salary_currency": None,
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
    assert result.salary_min == 150000


async def test_evaluate_job_non_integer_float_salary_becomes_none():
    caller = make_caller(
        json.dumps(
            {
                "score": 7.0,
                "score_notes": "x",
                "caveats": [],
                "salary_min": 150000.5,
                "salary_max": None,
                "salary_currency": None,
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
    assert result.salary_min is None
