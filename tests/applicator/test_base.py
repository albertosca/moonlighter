import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from candidatador.applicator.base import ApplicationDraft, generate_answers

MOCK_ANSWERS = json.dumps({
    "Why do you want to work here?": "I admire Stripe's mission to increase GDP of the internet.",
    "Describe your distributed systems experience": "At Acme, I built high-throughput pipelines with Elixir/OTP handling 50k events/sec.",
})

PROFILE = {
    "skills": [{"name": "Elixir/Phoenix", "years": 8, "level": "expert"}],
    "experience": [{"role": "Senior SWE", "company": "Acme", "highlights": ["Built OTP systems"]}],
}

@pytest.mark.asyncio
async def test_generate_answers_returns_draft():
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=MOCK_ANSWERS)]
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    result = await generate_answers(
        company="Stripe",
        title="Sr Engineer",
        description="Build payments infra.",
        fields=["Why do you want to work here?", "Describe your distributed systems experience"],
        profile=PROFILE,
        model="claude-sonnet-4-6",
        _client=mock_client,
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
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text="not json")]))
    result = await generate_answers(company="Co", title="Eng", description="desc", fields=["Q1"], profile=PROFILE, model="test", _client=mock_client)
    assert isinstance(result, ApplicationDraft)
    assert result.error is not None
    assert result.answers == {}


async def test_generate_answers_llm_exception():
    """LLM raises exception → ApplicationDraft with error string."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))
    result = await generate_answers(company="Co", title="Eng", description="desc", fields=["Q1"], profile=PROFILE, model="test", _client=mock_client)
    assert result.error is not None
    assert "API error" in result.error


async def test_generate_answers_job_id_propagated():
    """job_id passed to generate_answers appears in returned draft."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=json.dumps({"Q1": "answer"}))]))
    result = await generate_answers(company="Co", title="Eng", description="desc", fields=["Q1"], profile=PROFILE, model="test", job_id=42, _client=mock_client)
    assert result.job_id == 42


async def test_generate_answers_description_capped():
    """description longer than 4000 chars is capped in the prompt."""
    long_description = "y" * 6000
    captured = []

    async def capture_create(**kwargs):
        captured.append(kwargs["messages"][0]["content"])
        return MagicMock(content=[MagicMock(text=json.dumps({"Q1": "answer"}))])

    mock_client = MagicMock()
    mock_client.messages.create = capture_create

    await generate_answers(company="Co", title="Eng", description=long_description, fields=["Q1"], profile=PROFILE, model="test", _client=mock_client)
    assert "y" * 4001 not in captured[0]
    assert "y" * 3999 in captured[0]


async def test_generate_answers_fields_in_prompt():
    """All field names appear in the LLM prompt."""
    captured = []

    async def capture_create(**kwargs):
        captured.append(kwargs["messages"][0]["content"])
        return MagicMock(content=[MagicMock(text=json.dumps({"Why Stripe?": "ans", "Years exp?": "ans"}))])

    mock_client = MagicMock()
    mock_client.messages.create = capture_create

    await generate_answers(company="Stripe", title="Eng", description="desc", fields=["Why Stripe?", "Years exp?"], profile=PROFILE, model="test", _client=mock_client)
    assert "Why Stripe?" in captured[0]
    assert "Years exp?" in captured[0]


def test_application_draft_with_error():
    """ApplicationDraft with error field is accessible."""
    draft = ApplicationDraft(job_id=1, answers={}, form_fields=[], error="timeout")
    assert draft.error == "timeout"
    assert draft.answers == {}


async def test_generate_answers_uses_injected_client():
    """When _client is passed, anthropic.AsyncAnthropic() is NOT instantiated."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=json.dumps({"Q": "a"}))]))
    with patch("candidatador.applicator.base.anthropic.AsyncAnthropic") as mock_anthropic:
        await generate_answers(company="Co", title="Eng", description="desc", fields=["Q"], profile=PROFILE, model="test", _client=mock_client)
    mock_anthropic.assert_not_called()
