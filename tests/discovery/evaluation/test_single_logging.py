"""Tests for the debug and warning records evaluate_job writes."""

import json
import logging
from unittest.mock import AsyncMock

import pytest

from moonlighter.discovery.evaluation.single import evaluate_job
from tests.discovery.evaluation.fake_evaluation import (
    MOCK_LLM_RESPONSE,
    evaluate_once,
    make_caller,
    warning_records,
)


@pytest.mark.asyncio
async def test_evaluate_job_logs_score(caplog):
    good_response = json.dumps(
        {
            "score": 8.5,
            "score_notes": "Good match",
            "caveats": [],
            "salary_min": 100000,
            "salary_max": 150000,
            "salary_currency": "USD",
            "salary_source": "stated",
        }
    )
    mock_caller = AsyncMock(return_value=good_response)

    with caplog.at_level(logging.DEBUG, logger="moonlighter.discovery.evaluation.single"):
        await evaluate_job(
            company="Stripe",
            title="Backend Engineer",
            description="Python, distributed systems",
            profile={"name": "Alberto"},
            _caller=mock_caller,
            location=None,
            remote_type=None,
        )

    assert "Stripe" in caplog.text
    assert "Backend Engineer" in caplog.text
    assert "8.5" in caplog.text


async def test_evaluate_job_logs_what_it_evaluates_and_the_score(caplog):
    with caplog.at_level(logging.DEBUG):
        await evaluate_once(make_caller(MOCK_LLM_RESPONSE))
    messages = [record.getMessage() for record in caplog.records if record.levelno == logging.DEBUG]
    assert "evaluating Co/Eng" in messages
    assert "→ score 8.5 (Co)" in messages


async def test_a_parse_failure_is_logged_as_a_warning_with_the_traceback(caplog):
    with caplog.at_level(logging.DEBUG):
        await evaluate_once(make_caller("not json"))
    (record,) = warning_records(caplog)
    assert record.getMessage() == "evaluator: parse error for Co/Eng"
    assert record.exc_info is not None


async def test_a_failed_call_is_logged_as_a_warning_with_the_traceback(caplog):
    async def caller(prompt, model, cache_prefix=None):
        raise RuntimeError("boom")

    with caplog.at_level(logging.DEBUG):
        await evaluate_once(caller)
    (record,) = warning_records(caplog)
    assert record.getMessage() == "evaluator: error for Co/Eng — boom"
    assert record.exc_info is not None
