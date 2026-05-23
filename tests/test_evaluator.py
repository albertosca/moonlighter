import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
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


async def test_evaluate_job_score_10():
    """Score of 10.0 is preserved exactly."""
    response = json.dumps({"score": 10.0, "score_notes": "Perfect match.", "caveats": [], "salary_min": None, "salary_max": None, "salary_currency": None, "salary_source": None})
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=response)]))
    result = await evaluate_job(company="Co", title="Eng", description="desc", profile=PROFILE, model="test", _client=mock_client)
    assert result.score == 10.0


async def test_evaluate_job_partial_json_missing_salary():
    """JSON with no salary fields → salary_* all None."""
    response = json.dumps({"score": 7.0, "score_notes": "Good match.", "caveats": []})
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=response)]))
    result = await evaluate_job(company="Co", title="Eng", description="desc", profile=PROFILE, model="test", _client=mock_client)
    assert result.salary_min is None
    assert result.salary_max is None
    assert result.salary_currency is None
    assert result.salary_source is None


async def test_evaluate_job_caveats_empty_array():
    """Empty caveats array returns []."""
    response = json.dumps({"score": 7.0, "score_notes": "Ok.", "caveats": [], "salary_min": None, "salary_max": None, "salary_currency": None, "salary_source": None})
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=response)]))
    result = await evaluate_job(company="Co", title="Eng", description="desc", profile=PROFILE, model="test", _client=mock_client)
    assert result.caveats == []


async def test_evaluate_job_caveats_multiple():
    """Multiple caveats are all preserved."""
    response = json.dumps({"score": 5.0, "score_notes": "Mixed.", "caveats": ["US citizens only", "requires visa", "must relocate"], "salary_min": None, "salary_max": None, "salary_currency": None, "salary_source": None})
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=response)]))
    result = await evaluate_job(company="Co", title="Eng", description="desc", profile=PROFILE, model="test", _client=mock_client)
    assert len(result.caveats) == 3
    assert "US citizens only" in result.caveats


async def test_evaluate_job_llm_exception_returns_zero():
    """Any non-JSON exception → score=0.0 with 'evaluation error' in notes."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("network timeout"))
    result = await evaluate_job(company="Co", title="Eng", description="desc", profile=PROFILE, model="test", _client=mock_client)
    assert result.score == 0.0
    assert "evaluation error" in result.score_notes.lower()


async def test_evaluate_job_description_capped_at_8000():
    """description longer than 8000 chars is truncated before sending to LLM."""
    long_description = "x" * 10000
    captured_prompt = []
    response = json.dumps({"score": 5.0, "score_notes": "ok", "caveats": [], "salary_min": None, "salary_max": None, "salary_currency": None, "salary_source": None})

    async def capture_create(**kwargs):
        captured_prompt.append(kwargs["messages"][0]["content"])
        return MagicMock(content=[MagicMock(text=response)])

    mock_client = MagicMock()
    mock_client.messages.create = capture_create

    await evaluate_job(company="Co", title="Eng", description=long_description, profile=PROFILE, model="test", _client=mock_client)
    assert len(captured_prompt) == 1
    # The prompt contains the description (capped at 8000), not 10000 x's
    assert "x" * 8001 not in captured_prompt[0]
    assert "x" * 7999 in captured_prompt[0]


async def test_evaluate_job_uses_injected_client():
    """When _client is passed, anthropic.AsyncAnthropic() is NOT instantiated."""
    response = json.dumps({"score": 5.0, "score_notes": "ok", "caveats": [], "salary_min": None, "salary_max": None, "salary_currency": None, "salary_source": None})
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=response)]))
    with patch("candidatador.evaluator.anthropic.AsyncAnthropic") as mock_anthropic:
        await evaluate_job(company="Co", title="Eng", description="desc", profile=PROFILE, model="test", _client=mock_client)
    mock_anthropic.assert_not_called()


async def test_evaluate_job_salary_source_preserved():
    """salary_source from LLM response is preserved in result."""
    response = json.dumps({"score": 8.0, "score_notes": "Great.", "caveats": [], "salary_min": 150000, "salary_max": 200000, "salary_currency": "USD", "salary_source": "stated"})
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=response)]))
    result = await evaluate_job(company="Co", title="Eng", description="desc", profile=PROFILE, model="test", _client=mock_client)
    assert result.salary_source == "stated"
    assert result.salary_min == 150000


# ── LLM JSON parsing robustness ───────────────────────────────────────────────

async def test_evaluate_job_strips_markdown_fence():
    """LLM retorna JSON dentro de ```json ... ``` → parsed corretamente, score válido."""
    payload = {"score": 7.5, "score_notes": "Good.", "caveats": [], "salary_min": None, "salary_max": None, "salary_currency": None, "salary_source": None}
    wrapped = f"```json\n{json.dumps(payload)}\n```"
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=wrapped)]))
    result = await evaluate_job(company="Co", title="Eng", description="desc", profile=PROFILE, model="test", _client=mock_client)
    assert result.score == 7.5


async def test_evaluate_job_strips_markdown_fence_without_json_label():
    """LLM retorna JSON dentro de ``` ... ``` (sem 'json') → parsed corretamente."""
    payload = {"score": 6.0, "score_notes": "Ok.", "caveats": [], "salary_min": None, "salary_max": None, "salary_currency": None, "salary_source": None}
    wrapped = f"```\n{json.dumps(payload)}\n```"
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=wrapped)]))
    result = await evaluate_job(company="Co", title="Eng", description="desc", profile=PROFILE, model="test", _client=mock_client)
    assert result.score == 6.0


async def test_evaluate_job_strips_leading_prose():
    """LLM retorna texto introdutório seguido do JSON → JSON extraído e parsed."""
    payload = {"score": 8.0, "score_notes": "Great.", "caveats": [], "salary_min": None, "salary_max": None, "salary_currency": None, "salary_source": None}
    with_prose = f"Here is my evaluation:\n\n{json.dumps(payload)}"
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text=with_prose)]))
    result = await evaluate_job(company="Co", title="Eng", description="desc", profile=PROFILE, model="test", _client=mock_client)
    assert result.score == 8.0
