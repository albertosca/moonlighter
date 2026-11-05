"""Pins the gaps file questions become, and when they name the CV to attach."""

import pytest
from moonlighter.application.assisted.composition.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

from tests.application.assisted.composition.composer.sample_inputs import (
    JOB,
    PROFILE,
    answers_anything,
)


@pytest.mark.asyncio
async def test_a_file_question_is_always_a_gap_because_a_file_cannot_be_pasted():
    question = FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, answers_anything)
    assert composed[0].answer is None
    assert "upload" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_file_gap_names_the_cv_to_attach_when_one_is_configured(tmp_path):
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"%PDF-1.4")
    question = FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True)
    composed = await compose_answers(
        [question], PROFILE, {"cv": {"default": str(cv_path)}}, JOB, answers_anything
    )
    assert str(cv_path) in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_file_gap_still_appears_when_no_cv_is_configured():
    question = FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, answers_anything)
    assert composed[0].answer is None
    assert "no CV is configured" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_cv_file_gap_names_the_tailored_pdf_with_review_instruction(tmp_path):
    tailored = tmp_path / "7"
    tailored.mkdir()
    cv_path = tailored / "cv.pdf"
    cv_path.write_bytes(b"%PDF-1.5\n...\n%%EOF\n")  # real-shaped: resolve_cv_path sniffs it
    question = FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True)
    job = {**JOB, "id": 7}
    composed = await compose_answers(
        [question], PROFILE, {"cv": {"generated_dir": str(tmp_path)}}, job, answers_anything
    )
    assert str(cv_path) in composed[0].gap_reason
    assert "tailored for this job — review it before uploading" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_non_cv_file_gap_does_not_name_the_cv(tmp_path):
    """A "Cover letter" file field whose gap says "upload this file yourself:
    <the CV>" instructs the operator to attach the wrong document — found on
    the GitLab gate sheet (2026-08-13). Only CV-shaped labels get the path.
    """
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"%PDF-1.4")
    question = FormQuestion(label="Cover Letter", kind=QuestionKind.FILE, required=False)
    composed = await compose_answers(
        [question], PROFILE, {"cv": {"default": str(cv_path)}}, JOB, answers_anything
    )
    assert composed[0].answer is None
    assert str(cv_path) not in composed[0].gap_reason
    assert "upload" in composed[0].gap_reason
