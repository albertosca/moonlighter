"""Pins the exact wording of every gap reason the other tests check only in part."""

import pytest

from moonlighter.application.assisted.composition.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from tests.application.assisted.composition.composer.sample_inputs import JOB, PROFILE, never_called


def replying(reply: str):
    async def caller(prompt: str, model: str) -> str:
        return reply

    return caller


async def gap_for(question: FormQuestion, caller=never_called, **inputs) -> str | None:
    composed = await compose_answers(
        [question],
        inputs.get("profile", PROFILE),
        inputs.get("config", {}),
        inputs.get("job", JOB),
        caller,
    )
    return composed[0].gap_reason


@pytest.mark.asyncio
async def test_the_configured_cv_gap_reads_upload_this_file_yourself(tmp_path):
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"%PDF-1.4")
    question = FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True)
    reason = await gap_for(question, config={"cv": {"default": str(cv_path)}})
    assert reason == f"upload this file yourself: {cv_path}"


@pytest.mark.asyncio
async def test_the_tailored_cv_gap_appends_the_review_instruction(tmp_path):
    tailored = tmp_path / "7"
    tailored.mkdir()
    cv_path = tailored / "cv.pdf"
    cv_path.write_bytes(b"%PDF-1.5\n...\n%%EOF\n")
    question = FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True)
    reason = await gap_for(
        question, config={"cv": {"generated_dir": str(tmp_path)}}, job={**JOB, "id": 7}
    )
    assert reason == (
        f"upload this file yourself: {cv_path} (tailored for this job — review it before uploading)"
    )


@pytest.mark.asyncio
async def test_the_file_gaps_without_a_cv_path_read_exactly():
    cv_question = FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True)
    other_question = FormQuestion(label="Cover Letter", kind=QuestionKind.FILE, required=False)
    assert await gap_for(cv_question) == "upload a file yourself — no CV is configured"
    assert await gap_for(other_question) == "upload a file yourself"


@pytest.mark.asyncio
async def test_the_compliance_and_sensitive_gaps_read_exactly():
    compliance = FormQuestion(
        label="I certify that the information provided is true and complete",
        kind=QuestionKind.TEXT,
        required=True,
    )
    sensitive = FormQuestion(label="References", kind=QuestionKind.LONG_TEXT, required=True)
    assert await gap_for(compliance) == "declaration/compliance question — answer this yourself"
    assert await gap_for(sensitive) == "demographic/reference question — answer this yourself"


@pytest.mark.asyncio
async def test_the_review_sentinel_gap_reads_exactly():
    question = FormQuestion(
        label="Will you require visa sponsorship?", kind=QuestionKind.TEXT, required=True
    )
    assert await gap_for(question) == "no defensible answer here — answer this yourself"


@pytest.mark.asyncio
async def test_the_operator_directed_gap_names_the_marker_it_found():
    question = FormQuestion(label="Portfolio walkthrough", kind=QuestionKind.TEXT, required=True)
    reason = await gap_for(question, replying("the candidate will provide a walkthrough later"))
    assert reason == 'the model addressed the operator ("the candidate...") — answer this yourself'


@pytest.mark.asyncio
async def test_the_option_mismatch_gaps_read_exactly():
    single = FormQuestion(
        label="Which team appeals to you most?",
        kind=QuestionKind.SINGLE_SELECT,
        required=True,
        options=("Platform", "Product"),
    )
    multi = FormQuestion(
        label="Which of these do you know?",
        kind=QuestionKind.MULTI_SELECT,
        required=True,
        options=("Ruby", "Elixir"),
    )
    single_reason = await gap_for(single, replying("Marketing"))
    multi_reason = await gap_for(multi, replying("COBOL"))
    assert single_reason == "no offered option matches — pick one yourself"
    assert multi_reason == "no offered option matches — pick yourself"


@pytest.mark.asyncio
async def test_the_spend_limit_gap_reads_exactly():
    async def spent(prompt: str, model: str) -> str:
        raise RuntimeError("Claude AI usage spend limit reached")

    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    assert await gap_for(question, spent) == (
        "the LLM spend limit was hit — generation aborted, answer this yourself"
    )
