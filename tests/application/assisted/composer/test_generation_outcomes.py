"""Pins what an empty, UNKNOWN or failed generation becomes, and the spend-limit abort."""

import pytest
from moonlighter.application.assisted.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

from tests.application.assisted.composer.sample_inputs import JOB, PROFILE


@pytest.mark.asyncio
async def test_an_empty_generated_answer_becomes_a_gap_rather_than_an_empty_field():
    async def returns_nothing(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return "   "

    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, returns_nothing)
    assert composed[0].answer is None


@pytest.mark.asyncio
async def test_an_llm_failure_becomes_a_gap_and_does_not_abort_the_other_questions():
    async def explodes(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        raise RuntimeError("model unavailable")

    questions = [
        FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True),
        FormQuestion(label="First Name", kind=QuestionKind.TEXT, required=True),
    ]
    composed = await compose_answers(questions, PROFILE, {}, JOB, explodes)
    assert composed[0].answer is None
    assert composed[1].answer == "Alberto"


# ── IMPORTANT 5: generation failure vs a genuine UNKNOWN ─────────────────────


@pytest.mark.asyncio
async def test_an_llm_error_reports_generation_failure_not_a_knowledge_gap():
    """Before this fix, `except Exception: return None` in _generate made a
    spend-limit or network error read exactly like a genuine UNKNOWN -- "no basis
    in your profile to answer" is a fact about the candidate, and an LLM outage
    is a fact about the tool run. They must not share a gap reason."""

    async def explodes(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        # A non-spend failure: the spend-limit string now routes to its own
        # abort path (see test_spend_limit_aborts_remaining_generations).
        raise RuntimeError("backend exploded")

    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, explodes)
    assert composed[0].answer is None
    assert composed[0].gap_reason == "answer generation failed — answer this yourself"


@pytest.mark.asyncio
async def test_a_genuine_unknown_keeps_the_no_basis_reason():
    async def replies_unknown(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return "UNKNOWN"

    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, replies_unknown)
    assert composed[0].answer is None
    assert composed[0].gap_reason == "no basis in your profile to answer"


@pytest.mark.asyncio
async def test_spend_limit_aborts_remaining_generations():
    # One doomed LLM call per question after the limit is pure latency; the
    # first spend-limit failure marks every remaining generated answer as a
    # gap without another call. Deterministic fields are unaffected.
    calls = {"n": 0}

    async def spent(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        calls["n"] += 1
        raise RuntimeError("Claude AI usage spend limit reached")

    questions = [
        FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True),
        FormQuestion(label="Why now?", kind=QuestionKind.LONG_TEXT, required=True),
        FormQuestion(label="Email", kind=QuestionKind.TEXT, required=True),
    ]
    composed = await compose_answers(questions, PROFILE, {}, JOB, spent)

    assert calls["n"] == 1
    assert composed[0].answer is None
    assert "spend limit" in composed[0].gap_reason
    assert composed[1].answer is None
    assert "spend limit" in composed[1].gap_reason
    assert composed[2].answer == PROFILE["email"]  # deterministic, no LLM needed


@pytest.mark.asyncio
async def test_a_non_spend_failure_still_tries_each_question():
    calls = {"n": 0}

    async def flaky(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        calls["n"] += 1
        raise RuntimeError("connection reset")

    questions = [
        FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True),
        FormQuestion(label="Why now?", kind=QuestionKind.LONG_TEXT, required=True),
    ]
    composed = await compose_answers(questions, PROFILE, {}, JOB, flaky)
    assert calls["n"] == 2
    assert all("generation failed" in item.gap_reason for item in composed)
