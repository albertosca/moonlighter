"""Tests for the caller, model and logging evaluate_job uses."""

import json
from unittest.mock import patch

from moonlighter.discovery.evaluation.single import evaluate_job

from tests.discovery.evaluation.evaluation_fakes import (
    JOB_DESCRIPTION,
    MOCK_LLM_RESPONSE,
    PROFILE,
    evaluate_once,
    make_caller,
    recording_caller,
)


async def test_evaluate_job_description_capped_at_8000():
    """Body (company + title + description) longer than 8000 chars is capped before sending to LLM."""
    long_description = "x" * 10000
    captured_prompt = []
    response = json.dumps(
        {
            "score": 5.0,
            "score_notes": "ok",
            "caveats": [],
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_source": None,
        }
    )

    async def capture_caller(prompt, model, cache_prefix=None):
        captured_prompt.append(prompt)
        return response

    await evaluate_job(
        company="Co",
        title="Eng",
        description=long_description,
        profile=PROFILE,
        model="test",
        _caller=capture_caller,
        location=None,
        remote_type=None,
    )
    assert len(captured_prompt) == 1
    assert "x" * 8001 not in captured_prompt[0]
    # The body cap is 8000, minus metadata ("Company: Co\nTitle: Eng\nDescription:\n" = 36 chars)
    # leaves 7964 chars for description.
    assert "x" * 7964 in captured_prompt[0]


async def test_evaluate_job_uses_injected_caller():
    """When _caller is passed, make_api_caller() is NOT called."""
    response = json.dumps(
        {
            "score": 5.0,
            "score_notes": "ok",
            "caveats": [],
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_source": None,
        }
    )
    called = []

    async def tracking_caller(prompt, model, cache_prefix=None):
        called.append((prompt, model))
        return response

    with patch("moonlighter.discovery.evaluation.single.make_api_caller") as mock_factory:
        await evaluate_job(
            company="Co",
            title="Eng",
            description="desc",
            profile=PROFILE,
            model="test",
            _caller=tracking_caller,
            location=None,
            remote_type=None,
        )
    mock_factory.assert_not_called()
    assert len(called) == 1


async def test_evaluate_job_caller_receives_model():
    """The model argument is forwarded to the caller."""
    received_models = []

    async def capture_caller(prompt, model, cache_prefix=None):
        received_models.append(model)
        return json.dumps(
            {
                "score": 5.0,
                "score_notes": "ok",
                "caveats": [],
                "salary_min": None,
                "salary_max": None,
                "salary_currency": None,
                "salary_source": None,
            }
        )

    await evaluate_job(
        company="Co",
        title="Eng",
        description="desc",
        profile=PROFILE,
        model="custom-model-xyz",
        _caller=capture_caller,
        location=None,
        remote_type=None,
    )
    assert received_models == ["custom-model-xyz"]


async def test_evaluate_job_passes_cache_prefix():
    """evaluate_job must send the profile/instructions as cache_prefix and the job as the prompt."""
    captured = {}

    async def caller(prompt, model, cache_prefix=None):
        captured["prefix"] = cache_prefix
        captured["dynamic"] = prompt
        return '{"score": 8.0, "score_notes": "x", "caveats": []}'

    await evaluate_job(
        "Co", "Eng", "JD here", {"skills": ["python"]}, "m", caller, location=None, remote_type=None
    )
    assert captured["prefix"] is not None
    assert "python" in captured["prefix"]
    assert "JD here" in captured["dynamic"]
    assert "JD here" not in captured["prefix"]  # job is not in the cacheable prefix


async def test_evaluate_job_builds_default_caller_when_none():
    """_caller=None → usa make_api_caller() como fallback (single.py)."""
    fake = make_caller(MOCK_LLM_RESPONSE)
    with patch(
        "moonlighter.discovery.evaluation.single.make_api_caller", return_value=fake
    ) as factory:
        result = await evaluate_job(
            company="Co",
            title="Eng",
            description=JOB_DESCRIPTION,
            profile=PROFILE,
            _caller=None,
            location=None,
            remote_type=None,
        )
    factory.assert_called_once()
    assert result.score == 8.5


async def test_the_default_model_is_claude_sonnet_4_6():
    caller, calls = recording_caller(MOCK_LLM_RESPONSE)
    await evaluate_once(caller)
    assert calls[0][1] == "claude-sonnet-4-6"
