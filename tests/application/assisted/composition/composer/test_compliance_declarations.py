"""Pins that declaration and compliance questions never reach the LLM."""

import pytest
from moonlighter.application.assisted.composition.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

from tests.application.assisted.composition.composer.sample_inputs import JOB, PROFILE, never_called

GYMPASS_CONFLICT_OPTIONS = (
    (
        "I currently hold or have previously held a position, role, or affiliation "
        "with a public body, government entity, state-owned enterprise, political "
        "party, or international organization."
    ),
    "I engage in external professional activity.",
    "I have nothing to declare.",
)


@pytest.mark.asyncio
async def test_a_compliance_declaration_never_reaches_the_llm():
    # Live incident 2026-08-21 (gympass #3416): the model picked the public-body
    # affiliation option for a candidate who never held one — a signed false
    # statement. Declaration questions are deterministic-guard territory.
    question = FormQuestion(
        label="Conflict of Interest Declaration",
        kind=QuestionKind.MULTI_SELECT,
        required=True,
        options=GYMPASS_CONFLICT_OPTIONS,
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].answer is None
    assert "compliance" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_compliance_detected_by_options_under_a_neutral_label():
    question = FormQuestion(
        label="Please select all that apply",
        kind=QuestionKind.MULTI_SELECT,
        required=True,
        options=GYMPASS_CONFLICT_OPTIONS,
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].answer is None
    assert "compliance" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_text_certification_question_is_also_guarded():
    question = FormQuestion(
        label="I certify that the information provided is true and complete",
        kind=QuestionKind.TEXT,
        required=True,
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].answer is None
    assert "compliance" in composed[0].gap_reason
