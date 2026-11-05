"""Pins the failures the composer lets escape instead of turning them into gaps."""

import asyncio

import pytest
from moonlighter.application.assisted.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

from tests.application.assisted.composer.sample_inputs import JOB, PROFILE, answers_anything


@pytest.mark.asyncio
async def test_a_non_numeric_job_id_escapes_from_the_cv_file_gap(tmp_path):
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"%PDF-1.4")
    question = FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True)
    with pytest.raises(ValueError, match="invalid literal for int"):
        await compose_answers(
            [question],
            PROFILE,
            {"cv": {"default": str(cv_path)}},
            {**JOB, "id": "abc"},
            answers_anything,
        )


@pytest.mark.asyncio
async def test_a_cancelled_llm_call_is_not_turned_into_a_gap():
    async def cancelled(prompt: str, model: str) -> str:
        raise asyncio.CancelledError

    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    with pytest.raises(asyncio.CancelledError):
        await compose_answers([question], PROFILE, {}, JOB, cancelled)
