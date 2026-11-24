"""Pins the CompositionContext that carries everything compose_answers needs besides the questions."""

import dataclasses

import pytest

from moonlighter.application.assisted.composition.composer import (
    CompositionContext,
    compose_answers,
)
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.core.config.loading import build_config
from tests.application.assisted.composition.composer.sample_inputs import (
    JOB,
    PROFILE,
    answers_anything,
)


def test_two_contexts_never_share_a_default_cache():
    first = CompositionContext(PROFILE, build_config({}), JOB, answers_anything)
    second = CompositionContext(PROFILE, build_config({}), JOB, answers_anything)

    first.job_cache["question"] = {"answer": "x", "kind": "text"}
    first.answer_bank["question"] = "y"

    assert second.job_cache == {}
    assert second.answer_bank == {}


def test_the_context_is_frozen():
    context = CompositionContext(PROFILE, build_config({}), JOB, answers_anything)
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.job = {}  # type: ignore[misc]  # the assignment under test


@pytest.mark.asyncio
async def test_a_generated_answer_lands_in_the_cache_the_context_carries():
    question = FormQuestion(label="Why us?", kind=QuestionKind.TEXT, required=True)
    context = CompositionContext(PROFILE, build_config({}), JOB, answers_anything)

    await compose_answers([question], context)

    assert context.job_cache["Why us?"] == {"answer": "a generated answer", "kind": "text"}
