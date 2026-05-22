import pytest
import json
from unittest.mock import MagicMock, AsyncMock
from candidatador.evaluator import evaluate_job, EvaluationResult

MOCK_LLM_RESPONSE = json.dumps({
    "score": 8.5,
    "score_notes": "Excelente match em Elixir/Phoenix. Stack alinhada. Remoto total.",
    "caveats": ["Must overlap EST timezone by 4h"],
    "salary_min": 180000,
    "salary_max": 220000,
    "salary_currency": "USD",
    "salary_source": "llm_estimate",
})

PROFILE = {
    "skills": [{"name": "Elixir/Phoenix", "years": 8, "level": "expert"}],
    "criteria": {
        "hard_filters": ["descarta se exigir .NET"],
        "soft_filters": ["preferência por série A–C"],
    },
}

JD = "Senior Elixir Engineer. Remote. Build distributed systems with Elixir/OTP."

@pytest.mark.asyncio
async def test_evaluate_job_returns_result():
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=MOCK_LLM_RESPONSE)]
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    result = await evaluate_job(
        company="Acme", title="Sr Elixir Eng",
        description=JD, profile=PROFILE, model="claude-sonnet-4-6",
        _client=mock_client,
    )

    assert isinstance(result, EvaluationResult)
    assert result.score == 8.5
    assert result.salary_min == 180000
    assert "EST" in result.caveats[0]

@pytest.mark.asyncio
async def test_evaluate_job_handles_malformed_json():
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="not json")]
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    result = await evaluate_job(
        company="Acme", title="Eng",
        description="desc", profile=PROFILE, model="claude-sonnet-4-6",
        _client=mock_client,
    )

    assert result.score == 0.0
    assert "parse error" in result.score_notes.lower()
