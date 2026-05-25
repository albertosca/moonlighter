import pytest
import json
from unittest.mock import patch
from candidatador.applicator.base import ApplicationDraft, generate_answers

MOCK_ANSWERS = json.dumps({
    "Why do you want to work here?": "I admire Stripe's mission to increase GDP of the internet.",
    "Describe your distributed systems experience": "At Acme, I built high-throughput pipelines with Elixir/OTP handling 50k events/sec.",
})

PROFILE = {
    "skills": [{"name": "Elixir/Phoenix", "years": 8, "level": "expert"}],
    "experience": [{"role": "Senior SWE", "company": "Acme", "highlights": ["Built OTP systems"]}],
}


def _make_caller(text: str):
    async def caller(prompt, model):
        return text
    return caller


async def test_generate_answers_returns_draft():
    result = await generate_answers(
        company="Stripe",
        title="Sr Engineer",
        description="Build payments infra.",
        fields=["Why do you want to work here?", "Describe your distributed systems experience"],
        profile=PROFILE,
        model="claude-sonnet-4-6",
        _caller=_make_caller(MOCK_ANSWERS),
    )

    assert isinstance(result, ApplicationDraft)
    assert "Stripe" in result.answers.get("Why do you want to work here?", "")


def test_application_draft_serialization():
    draft = ApplicationDraft(
        job_id=1,
        answers={"q1": "answer1"},
        form_fields=["q1"],
    )
    assert draft.answers["q1"] == "answer1"


async def test_generate_answers_malformed_json():
    """LLM returns invalid JSON → ApplicationDraft with error, empty answers."""
    result = await generate_answers(company="Co", title="Eng", description="desc", fields=["Q1"], profile=PROFILE, model="test", _caller=_make_caller("not json"))
    assert isinstance(result, ApplicationDraft)
    assert result.error is not None
    assert result.answers == {}


async def test_generate_answers_llm_exception():
    """LLM raises exception → ApplicationDraft with error string."""
    async def failing_caller(prompt, model):
        raise Exception("API error")

    result = await generate_answers(company="Co", title="Eng", description="desc", fields=["Q1"], profile=PROFILE, model="test", _caller=failing_caller)
    assert result.error is not None
    assert "API error" in result.error


async def test_generate_answers_job_id_propagated():
    """job_id passed to generate_answers appears in returned draft."""
    result = await generate_answers(company="Co", title="Eng", description="desc", fields=["Q1"], profile=PROFILE, model="test", job_id=42, _caller=_make_caller(json.dumps({"Q1": "answer"})))
    assert result.job_id == 42


async def test_generate_answers_description_capped():
    """description longer than 4000 chars is capped in the prompt."""
    long_description = "y" * 6000
    captured = []

    async def capture_caller(prompt, model):
        captured.append(prompt)
        return json.dumps({"Q1": "answer"})

    await generate_answers(company="Co", title="Eng", description=long_description, fields=["Q1"], profile=PROFILE, model="test", _caller=capture_caller)
    assert "y" * 4001 not in captured[0]
    assert "y" * 3999 in captured[0]


async def test_generate_answers_fields_in_prompt():
    """All field names appear in the LLM prompt."""
    captured = []

    async def capture_caller(prompt, model):
        captured.append(prompt)
        return json.dumps({"Why Stripe?": "ans", "Years exp?": "ans"})

    await generate_answers(company="Stripe", title="Eng", description="desc", fields=["Why Stripe?", "Years exp?"], profile=PROFILE, model="test", _caller=capture_caller)
    assert "Why Stripe?" in captured[0]
    assert "Years exp?" in captured[0]


def test_application_draft_with_error():
    """ApplicationDraft with error field is accessible."""
    draft = ApplicationDraft(job_id=1, answers={}, form_fields=[], error="timeout")
    assert draft.error == "timeout"
    assert draft.answers == {}


async def test_generate_answers_uses_injected_caller():
    """When _caller is passed, _make_api_caller() is NOT called."""
    called = []

    async def tracking_caller(prompt, model):
        called.append((prompt, model))
        return json.dumps({"Q": "a"})

    with patch("candidatador.applicator.base._make_api_caller") as mock_factory:
        await generate_answers(company="Co", title="Eng", description="desc", fields=["Q"], profile=PROFILE, model="test", _caller=tracking_caller)
    mock_factory.assert_not_called()
    assert len(called) == 1


async def test_generate_answers_caller_receives_model():
    """The model argument is forwarded to the caller."""
    received_models = []

    async def capture_caller(prompt, model):
        received_models.append(model)
        return json.dumps({"Q": "answer"})

    await generate_answers(company="Co", title="Eng", description="desc", fields=["Q"], profile=PROFILE, model="my-special-model", _caller=capture_caller)
    assert received_models == ["my-special-model"]


# ── LLM JSON parsing robustness ───────────────────────────────────────────────

async def test_generate_answers_strips_markdown_fence():
    """LLM retorna respostas dentro de ```json ... ``` → parsed corretamente."""
    answers = {"Why Stripe?": "Great mission"}
    wrapped = f"```json\n{json.dumps(answers)}\n```"
    result = await generate_answers(company="Stripe", title="Eng", description="desc", fields=["Why Stripe?"], profile=PROFILE, model="test", _caller=_make_caller(wrapped))
    assert result.error is None
    assert result.answers.get("Why Stripe?") == "Great mission"


async def test_generate_answers_strips_leading_prose():
    """LLM retorna texto seguido do JSON → JSON extraído."""
    answers = {"Why here?": "Interesting work"}
    with_prose = f"Sure, here are the answers:\n{json.dumps(answers)}"
    result = await generate_answers(company="Co", title="Eng", description="desc", fields=["Why here?"], profile=PROFILE, model="test", _caller=_make_caller(with_prose))
    assert result.error is None
    assert result.answers.get("Why here?") == "Interesting work"
