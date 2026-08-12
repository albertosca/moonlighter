import pytest
from moonlighter.application.assisted.composer import ComposedAnswer, compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

PROFILE = {"name": "Alberto de Sá Cavalcanti de Albuquerque", "email": "a@example.com"}
JOB = {"title": "Staff Engineer", "company": "acme", "description": "..."}


async def never_called(prompt: str, model: str, cache_prefix: str | None = None) -> str:
    raise AssertionError("the LLM must not be consulted for a field the profile answers")


async def answers_anything(prompt: str, model: str, cache_prefix: str | None = None) -> str:
    return "a generated answer"


@pytest.mark.asyncio
async def test_a_profile_backed_field_is_answered_without_the_llm():
    questions = [FormQuestion(label="First Name", kind=QuestionKind.TEXT, required=True)]
    composed = await compose_answers(questions, PROFILE, {}, JOB, never_called)
    assert composed[0].answer == "Alberto"
    assert composed[0].gap_reason is None


@pytest.mark.asyncio
async def test_a_select_answer_must_be_one_of_the_offered_options():
    # The label deliberately avoids "sponsor"/"authoriz" — those words route through
    # pre_populate_answers' work-authorization rule (country-dependent, always answers
    # its own review sentinel when the country can't be inferred), which would settle
    # the question before the LLM callback below is ever consulted and defeat the point
    # of this test: that a genuinely LLM-generated answer outside the options is a gap.
    question = FormQuestion(
        label="Which team appeals to you most?",
        kind=QuestionKind.SINGLE_SELECT,
        required=True,
        options=("Platform", "Product"),
    )

    async def picks_something_else(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return "Marketing"

    composed = await compose_answers([question], PROFILE, {}, JOB, picks_something_else)
    assert composed[0].answer is None
    assert "option" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_select_answer_that_matches_an_option_is_kept_verbatim():
    question = FormQuestion(
        label="Which team appeals to you most?",
        kind=QuestionKind.SINGLE_SELECT,
        required=True,
        options=("Platform", "Product"),
    )

    async def picks_an_option(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return "product"

    composed = await compose_answers([question], PROFILE, {}, JOB, picks_an_option)
    assert composed[0].answer == "Product"


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


@pytest.mark.asyncio
async def test_a_file_question_is_always_a_gap_because_a_file_cannot_be_pasted():
    question = FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, answers_anything)
    assert composed[0].answer is None
    assert "upload" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_file_gap_names_the_cv_to_attach_when_one_is_configured(tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4")
    question = FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True)
    composed = await compose_answers(
        [question], PROFILE, {"cv": {"default": str(cv)}}, JOB, answers_anything
    )
    assert str(cv) in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_file_gap_still_appears_when_no_cv_is_configured():
    question = FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, answers_anything)
    assert composed[0].answer is None
    assert "no CV is configured" in composed[0].gap_reason


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


@pytest.mark.asyncio
async def test_the_prompt_carries_the_posting_so_the_answer_can_match_its_language():
    # Answers follow the language of the posting, and the only thing that makes that
    # possible is the description reaching the prompt together with the instruction.
    captured: dict[str, str] = {}

    async def capture(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        captured["prompt"] = prompt
        return "resposta"

    job = {**JOB, "description": "Vaga para pessoa desenvolvedora sênior, 100% remoto."}
    question = FormQuestion(label="Por que você?", kind=QuestionKind.LONG_TEXT, required=True)
    await compose_answers([question], PROFILE, {}, job, capture)

    assert "Vaga para pessoa desenvolvedora" in captured["prompt"]
    assert "same language as the job posting" in captured["prompt"]


def test_a_composed_answer_cannot_be_both_answered_and_a_gap():
    question = FormQuestion(label="First Name", kind=QuestionKind.TEXT, required=True)
    with pytest.raises(ValueError, match="never both or neither"):
        ComposedAnswer(question, "Alberto", "no basis in your profile to answer")


def test_a_composed_answer_cannot_be_neither_answered_nor_a_gap():
    question = FormQuestion(label="First Name", kind=QuestionKind.TEXT, required=True)
    with pytest.raises(ValueError, match="never both or neither"):
        ComposedAnswer(question, None, None)


@pytest.mark.asyncio
async def test_every_question_produces_exactly_one_entry_in_order():
    questions = [
        FormQuestion(label="First Name", kind=QuestionKind.TEXT, required=True),
        FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True),
        FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=False),
    ]
    composed = await compose_answers(questions, PROFILE, {}, JOB, answers_anything)
    assert [c.question.label for c in composed] == [q.label for q in questions]


@pytest.mark.asyncio
async def test_llm_prompt_carries_only_the_curated_profile():
    """references (a third party's contacts), preferences (the salary figure — E2)
    and demographics must never reach the prompt; the old applier path curated
    them out and the composer must too."""
    profile = {
        "name": "Alba Test",
        "summary": "Senior engineer.",
        "references": [{"name": "Ref Person", "email": "ref@example.com"}],
        "preferences": {"salary_target_brl_monthly": 35000},
        "demographics": {"gender": "prefer not to say"},
    }
    prompts: list[str] = []

    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        prompts.append(prompt)
        return "An answer."

    questions = [FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)]
    await compose_answers(questions, profile, {}, {"description": "A job."}, caller)

    assert len(prompts) == 1
    for leaked in ("Ref Person", "ref@example.com", "35000", "prefer not to say", "references"):
        assert leaked not in prompts[0]
    assert "Senior engineer." in prompts[0]


@pytest.mark.asyncio
async def test_salary_label_is_still_prepopulated_from_full_profile():
    """Curation is prompt-only: the deterministic salary rule still sees
    preferences and answers without any LLM call."""
    from unittest.mock import AsyncMock

    profile = {"preferences": {"salary_target_brl_monthly": 35000}}
    caller = AsyncMock(side_effect=AssertionError("LLM must not be called"))
    questions = [FormQuestion(label="Salary expectation", kind=QuestionKind.TEXT, required=True)]
    composed = await compose_answers(questions, profile, {}, {"description": "A job."}, caller)
    assert composed[0].answer == "35000"


OPERATOR_NOTE_REFERENCES = (
    "I can share professional references on request, so the candidate needs to "
    "supply names, roles and emails before submission."
)
OPERATOR_NOTE_ADDRESS = (
    "Note: no street address is available in the material provided - please "
    "supply before submitting."
)


@pytest.mark.asyncio
@pytest.mark.parametrize("note", [OPERATOR_NOTE_REFERENCES, OPERATOR_NOTE_ADDRESS])
async def test_operator_directed_prose_becomes_a_gap(note):
    """CANARY: these are the verbatim answers that shipped toward employers on
    2026-08-04 (references) and 2026-08-05 (address). The guard must bite on the
    failures that actually happened."""

    async def caller(prompt: str, model: str) -> str:
        return note

    questions = [FormQuestion(label="References", kind=QuestionKind.LONG_TEXT, required=False)]
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
