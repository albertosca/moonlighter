"""Pins that the work-authorization review sentinel becomes a gap on free-text questions."""

import pytest
from moonlighter.application.assisted.composition.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

from tests.application.assisted.composition.composer.sample_inputs import JOB, PROFILE, never_called


@pytest.mark.asyncio
async def test_a_work_auth_review_sentinel_becomes_a_gap_for_a_text_question():
    # Real-world shape: "sponsorship" routes through pre_populate_answers' work-auth
    # rule, which — with no work_authorization config and no job location to infer the
    # country from — answers its own review sentinel rather than leaving the field for
    # the LLM. Pins the CRITICAL this test set previously missed: on a free-text field
    # (unlike a select) nothing screened that sentinel before it reached the output as
    # a literal "__NEEDS_REVIEW__" answer, ready to be pasted into a real employer form.
    question = FormQuestion(
        label="Will you require visa sponsorship?", kind=QuestionKind.TEXT, required=True
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].answer is None
    assert composed[0].gap_reason
    assert "NEEDS_REVIEW" not in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_work_auth_review_sentinel_becomes_a_gap_for_a_long_text_question():
    question = FormQuestion(
        label="Do you require visa sponsorship now or in the future? Please explain.",
        kind=QuestionKind.LONG_TEXT,
        required=True,
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].answer is None
    assert composed[0].gap_reason
    assert "NEEDS_REVIEW" not in composed[0].gap_reason
