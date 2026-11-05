"""Pins the cross-job answer bank (Layer B): which question kinds it serves, and how."""

import pytest
from moonlighter.application.assisted.composition.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

from tests.application.assisted.composition.composer.sample_inputs import (
    JOB,
    PROFILE,
    answers_anything,
    never_called,
)


@pytest.mark.asyncio
async def test_an_answer_bank_hit_skips_the_llm_for_an_eligible_kind():
    question = FormQuestion(
        label="Do you have 5+ years of Python experience?",
        kind=QuestionKind.BOOLEAN,
        required=True,
    )
    bank = {"do you have 5+ years of python experience": "Yes"}
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called, answer_bank=bank)
    assert composed[0].answer == "Yes"


@pytest.mark.asyncio
async def test_the_answer_bank_is_never_consulted_for_long_text():
    question = FormQuestion(
        label="Why do you want to work here?", kind=QuestionKind.LONG_TEXT, required=True
    )
    bank = {"why do you want to work here": "a stale answer from a different company"}
    composed = await compose_answers(
        [question], PROFILE, {}, JOB, answers_anything, answer_bank=bank
    )
    assert composed[0].answer == "a generated answer"


@pytest.mark.asyncio
async def test_a_bank_answer_still_goes_through_option_matching():
    question = FormQuestion(
        label="Which team appeals to you most?",
        kind=QuestionKind.SINGLE_SELECT,
        required=True,
        options=("Platform", "Product"),
    )
    bank = {"which team appeals to you most": "product"}
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called, answer_bank=bank)
    assert composed[0].answer == "Product"


@pytest.mark.parametrize("label", ["Gender", "Veteran Status", "References"])
@pytest.mark.asyncio
async def test_a_sensitive_label_is_never_read_from_the_answer_bank_or_the_llm(label):
    # Demographics and references are excluded from the LLM's prompt
    # (profile_for_answers), and the is_sensitive_label guard above now keeps a
    # question SHAPED like this from ever reaching the LLM or the bank at all —
    # a stronger property than "the bank isn't consulted" alone: kind eligibility
    # (TEXT is bank-eligible) never even gets a chance to matter here. never_called
    # proves the LLM path specifically is unreachable; the populated `answer_bank`
    # proves a would-be bank hit is not served either.
    question = FormQuestion(label=label, kind=QuestionKind.TEXT, required=False)
    bank = {label.lower(): "a banked answer from a different company"}
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called, answer_bank=bank)
    assert composed[0].answer is None
    assert "demographic" in composed[0].gap_reason
