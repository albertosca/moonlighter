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
