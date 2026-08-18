import json

import pytest
from moonlighter.tracking.classification import ClassificationError, classify_response

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


# ── failure signalling (whole-branch Finding 1) ─────────────────────────────
#
# A classification that FAILED (the LLM raised, or its response could not be
# parsed) must be distinguishable from a successful classification of
# type == "unrelated" — otherwise sync_responses marks the message permanently
# processed and a real reply is lost forever the moment the model has a bad day.


@pytest.mark.asyncio
async def test_llm_call_raising_is_not_silently_treated_as_unrelated():
    async def raising_caller(prompt, model, cache_prefix=None):
        raise RuntimeError("network blip")

    with pytest.raises(ClassificationError):
        await classify_response({"subject": "x", "body": "y"}, STAGES, raising_caller)


@pytest.mark.asyncio
async def test_unparseable_llm_response_is_not_silently_treated_as_unrelated():
    call, _ = fake_llm("not JSON at all")
    with pytest.raises(ClassificationError):
        await classify_response({"subject": "x", "body": "y"}, STAGES, call)


@pytest.mark.asyncio
async def test_spend_limit_error_propagates_unwrapped_not_as_classification_error():
    """A spend-limit failure must be recognizable by the caller (via
    moonlighter.core.llm.is_spend_limit) so it can stop the sync loop instead of
    retrying every remaining message against a dead quota — wrapping it in
    ClassificationError like an ordinary failure would hide that distinction."""

    async def quota_exhausted_caller(prompt, model, cache_prefix=None):
        raise RuntimeError("rate limit exceeded, please retry later")

    with pytest.raises(RuntimeError) as exc_info:
        await classify_response({"subject": "x", "body": "y"}, STAGES, quota_exhausted_caller)
    assert not isinstance(exc_info.value, ClassificationError)
