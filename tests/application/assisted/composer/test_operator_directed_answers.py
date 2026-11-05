"""Pins that prose addressed to the operator becomes a gap, and what the guard lets through."""

import pytest
from moonlighter.application.assisted.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

from tests.application.assisted.composer.sample_inputs import JOB, PROFILE
from tests.application.operator_incidents import OPERATOR_NOTE_ADDRESS, OPERATOR_NOTE_REFERENCES


@pytest.mark.asyncio
@pytest.mark.parametrize("note", [OPERATOR_NOTE_REFERENCES, OPERATOR_NOTE_ADDRESS])
async def test_operator_directed_prose_becomes_a_gap(note):
    """CANARY: these are the verbatim answers that shipped toward employers on
    2026-08-04 (references) and 2026-08-05 (address). The guard must bite on the
    failures that actually happened.

    The label is deliberately neutral: what this canary pins is the ANSWER TEXT
    reaching the operator-directed guard, and the original "References" label is
    now intercepted upstream by is_sensitive_label — which would leave this
    passing without the operator guard ever running.
    """

    async def caller(prompt: str, model: str) -> str:
        return note

    questions = [
        FormQuestion(label="Anything else to add?", kind=QuestionKind.LONG_TEXT, required=False)
    ]
    composed = await compose_answers(questions, {}, {}, {"description": "A job."}, caller)
    assert composed[0].answer is None
    assert composed[0].gap_reason is not None
    assert "answer this yourself" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_ordinary_first_person_answer_passes():
    async def caller(prompt: str, model: str) -> str:
        return "I have led backend teams for six years and enjoy mentoring."

    questions = [
        FormQuestion(label="Tell us about you", kind=QuestionKind.LONG_TEXT, required=False)
    ]
    composed = await compose_answers(questions, {}, {}, {"description": "A job."}, caller)
    assert composed[0].answer is not None
    assert composed[0].gap_reason is None


@pytest.mark.asyncio
async def test_a_verbatim_option_naming_the_candidate_stays_selectable():
    """CANARY for MINOR 7 (spec B2): the operator-directed guard exists to catch
    the LLM narrating ABOUT the candidate in prose ("the candidate should..."),
    not to reject a legitimate, verbatim-correct dropdown option that happens to
    contain the phrase "the candidate". Gating the guard on `is_choice` keeps a
    real option like this pickable.
    """
    question = FormQuestion(
        label="Are you the candidate applying?",
        kind=QuestionKind.SINGLE_SELECT,
        required=True,
        options=("Yes, I am the candidate", "No"),
    )

    async def caller(prompt: str, model: str) -> str:
        return "Yes, I am the candidate"

    composed = await compose_answers([question], PROFILE, {}, JOB, caller)
    assert composed[0].answer == "Yes, I am the candidate"
    assert composed[0].gap_reason is None
