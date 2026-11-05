"""Pins the answers the profile settles without the LLM, and the one-entry-per-question shape."""

from unittest.mock import AsyncMock

import pytest
from moonlighter.application.assisted.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sheet import render_sheet

from tests.application.assisted.composer.sample_inputs import (
    JOB,
    PROFILE,
    answers_anything,
    never_called,
)


@pytest.mark.asyncio
async def test_a_profile_backed_field_is_answered_without_the_llm():
    questions = [FormQuestion(label="First Name", kind=QuestionKind.TEXT, required=True)]
    composed = await compose_answers(questions, PROFILE, {}, JOB, never_called)
    assert composed[0].answer == "Alberto"
    assert composed[0].gap_reason is None


@pytest.mark.asyncio
async def test_every_question_produces_exactly_one_entry_in_order():
    questions = [
        FormQuestion(label="First Name", kind=QuestionKind.TEXT, required=True),
        FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True),
        FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=False),
    ]
    composed = await compose_answers(questions, PROFILE, {}, JOB, answers_anything)
    assert [item.question.label for item in composed] == [question.label for question in questions]


@pytest.mark.asyncio
async def test_salary_label_is_still_prepopulated_from_full_profile():
    """Curation is prompt-only: the deterministic salary rule still sees
    preferences and answers without any LLM call."""
    profile = {"preferences": {"salary_target_brl_monthly": 35000}}
    caller = AsyncMock(side_effect=AssertionError("LLM must not be called"))
    questions = [FormQuestion(label="Salary expectation", kind=QuestionKind.TEXT, required=True)]
    composed = await compose_answers(questions, profile, {}, {"description": "A job."}, caller)
    assert composed[0].answer == "BRL 35.000/month"


# ── CRITICAL 2: presence vs truthiness for pre-populated answers ────────────


@pytest.mark.asyncio
async def test_salary_label_with_no_target_configured_becomes_a_gap_without_the_llm():
    """CRITICAL: `known.get(label) or await generate_answer(...)` treated the deliberate
    "" that _salary_expectation returns when no salary_target_brl_monthly is
    configured as absence, and fell through to the LLM to invent a figure — a
    direct violation of E2 (the salary figure must never reach the model)."""
    question = FormQuestion(label="Salary expectation", kind=QuestionKind.TEXT, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].answer is None
    assert composed[0].gap_reason == "no configured value for this field — answer this yourself"


@pytest.mark.asyncio
async def test_salary_gap_is_counted_in_the_sheet_footer():
    """The gap from the fix above must actually surface to the human, not just
    exist as a ComposedAnswer -- the sheet footer is where the human decides
    whether an application is ready to paste and submit."""
    question = FormQuestion(label="Salary expectation", kind=QuestionKind.TEXT, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    sheet = render_sheet(
        composed, job_title=JOB["title"], company=JOB["company"], apply_url="https://x/apply"
    )
    assert "1 of 1 need you" in sheet
    assert "no configured value for this field" in sheet


@pytest.mark.asyncio
async def test_a_label_absent_from_known_answers_still_calls_the_llm():
    """The other side of the presence/truthiness fix: a label pre_populate_answers
    never touched must still reach the LLM exactly as before."""
    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, answers_anything)
    assert composed[0].answer == "a generated answer"
    assert composed[0].gap_reason is None
