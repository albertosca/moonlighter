import json

import pytest
from moonlighter.tracking.classification import classify_response

STAGES = ["phone_screening", "technical_interview"]


def fake_llm(reply: str):
    captured: dict[str, str] = {}

    async def call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        captured["prompt"] = prompt
        return reply

    return call, captured


@pytest.mark.asyncio
async def test_the_prompt_offers_acknowledgement_as_a_type():
    # Without the category, a receipt is classified as the nearest wrong thing.
    call, captured = fake_llm(json.dumps({"type": "unrelated"}))
    await classify_response({"subject": "x", "body": "y"}, STAGES, call)
    assert "acknowledgement" in captured["prompt"]


@pytest.mark.asyncio
async def test_the_prompt_tells_the_model_a_receipt_is_not_a_screening():
    call, captured = fake_llm(json.dumps({"type": "unrelated"}))
    await classify_response({"subject": "x", "body": "y"}, STAGES, call)
    assert "has not started" in captured["prompt"]


@pytest.mark.asyncio
async def test_an_acknowledgement_carries_no_stage():
    call, _ = fake_llm(
        json.dumps({"type": "acknowledgement", "stage": "phone_screening", "new_stage": None})
    )
    result = await classify_response({"subject": "x", "body": "y"}, STAGES, call)
    assert result["type"] == "acknowledgement"
    assert result["stage"] is None
    assert result["new_stage"] is None
