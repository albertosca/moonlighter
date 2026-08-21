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
    assert composed[0].answer == "BRL 35.000/month"


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


@pytest.mark.asyncio
async def test_a_verbatim_option_naming_the_candidate_stays_selectable():
    """CANARY for MINOR 7 (spec B2): the operator-directed guard exists to catch
    the LLM narrating ABOUT the candidate in prose ("the candidate should..."),
    not to reject a legitimate, verbatim-correct dropdown option that happens to
    contain the phrase "the candidate". Gating the guard on `is_choice` keeps a
    real option like this pickable."""
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


# ── CRITICAL 2: presence vs truthiness for pre-populated answers ────────────


@pytest.mark.asyncio
async def test_salary_label_with_no_target_configured_becomes_a_gap_without_the_llm():
    """CRITICAL: `known.get(label) or await _generate(...)` treated the deliberate
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
    from moonlighter.application.assisted.sheet import render_sheet

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


# ── IMPORTANT 5: generation failure vs a genuine UNKNOWN ─────────────────────


@pytest.mark.asyncio
async def test_an_llm_error_reports_generation_failure_not_a_knowledge_gap():
    """Before this fix, `except Exception: return None` in _generate made a
    spend-limit or network error read exactly like a genuine UNKNOWN -- "no basis
    in your profile to answer" is a fact about the candidate, and an LLM outage
    is a fact about the tool run. They must not share a gap reason."""

    async def explodes(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        # A non-spend failure: the spend-limit string now routes to its own
        # abort path (see test_spend_limit_aborts_remaining_generations).
        raise RuntimeError("backend exploded")

    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, explodes)
    assert composed[0].answer is None
    assert composed[0].gap_reason == "answer generation failed — answer this yourself"


@pytest.mark.asyncio
async def test_a_genuine_unknown_keeps_the_no_basis_reason():
    async def replies_unknown(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return "UNKNOWN"

    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, replies_unknown)
    assert composed[0].answer is None
    assert composed[0].gap_reason == "no basis in your profile to answer"


@pytest.mark.asyncio
async def test_a_choice_prompt_tells_the_model_not_to_underclaim():
    """The model picked "minor limitations" for a profile that says English
    (fluent/native) — live on the Nubank shadow-run (2026-08-13), with the fact
    present in the curated prompt. The choice constraint must instruct it to
    pick the strongest option the profile supports."""
    captured: dict[str, str] = {}

    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        captured["prompt"] = prompt
        return "Fluent"

    question = FormQuestion(
        label="English level",
        kind=QuestionKind.SINGLE_SELECT,
        required=False,
        options=("Basic", "Fluent"),
    )
    profile = {"languages": ["English (fluent/native)"]}
    await compose_answers([question], profile, {}, {"description": "A job."}, caller)

    assert "strongest option the profile supports" in captured["prompt"]


@pytest.mark.asyncio
async def test_a_non_cv_file_gap_does_not_name_the_cv(tmp_path):
    """A "Cover letter" file field whose gap says "upload this file yourself:
    <the CV>" instructs the operator to attach the wrong document — found on
    the GitLab gate sheet (2026-08-13). Only CV-shaped labels get the path."""
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4")
    question = FormQuestion(label="Cover Letter", kind=QuestionKind.FILE, required=False)
    composed = await compose_answers(
        [question], PROFILE, {"cv": {"default": str(cv)}}, JOB, answers_anything
    )
    assert composed[0].answer is None
    assert str(cv) not in composed[0].gap_reason
    assert "upload" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_multi_select_accepts_several_verbatim_options():
    # "Which technologies do you know?" answered with ONE pick under-claims
    # structurally — a multi-select must let the model pick every option the
    # profile supports, newline-joined so the sheet can render each one.
    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return "Ruby\nElixir"

    question = FormQuestion(
        label="Which of these do you know?",
        kind=QuestionKind.MULTI_SELECT,
        required=True,
        options=("Ruby", "Elixir", ".NET"),
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, caller)
    assert composed[0].answer == "Ruby\nElixir"
    assert composed[0].gap_reason is None


@pytest.mark.asyncio
async def test_multi_select_prompt_allows_more_than_one():
    captured: dict[str, str] = {}

    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        captured["prompt"] = prompt
        return "Ruby"

    question = FormQuestion(
        label="Which of these do you know?",
        kind=QuestionKind.MULTI_SELECT,
        required=False,
        options=("Ruby", "Elixir"),
    )
    await compose_answers([question], PROFILE, {}, JOB, caller)
    assert "one or more" in captured["prompt"]


@pytest.mark.asyncio
async def test_multi_select_with_no_matching_option_is_a_gap():
    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return "COBOL"

    question = FormQuestion(
        label="Which of these do you know?",
        kind=QuestionKind.MULTI_SELECT,
        required=True,
        options=("Ruby", "Elixir"),
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, caller)
    assert composed[0].answer is None
    assert "pick" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_spend_limit_aborts_remaining_generations():
    # One doomed LLM call per question after the limit is pure latency; the
    # first spend-limit failure marks every remaining generated answer as a
    # gap without another call. Deterministic fields are unaffected.
    calls = {"n": 0}

    async def spent(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        calls["n"] += 1
        raise RuntimeError("Claude AI usage spend limit reached")

    questions = [
        FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True),
        FormQuestion(label="Why now?", kind=QuestionKind.LONG_TEXT, required=True),
        FormQuestion(label="Email", kind=QuestionKind.TEXT, required=True),
    ]
    composed = await compose_answers(questions, PROFILE, {}, JOB, spent)

    assert calls["n"] == 1
    assert composed[0].answer is None and "spend limit" in composed[0].gap_reason
    assert composed[1].answer is None and "spend limit" in composed[1].gap_reason
    assert composed[2].answer == PROFILE["email"]  # deterministic, no LLM needed


@pytest.mark.asyncio
async def test_a_non_spend_failure_still_tries_each_question():
    calls = {"n": 0}

    async def flaky(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        calls["n"] += 1
        raise RuntimeError("connection reset")

    questions = [
        FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True),
        FormQuestion(label="Why now?", kind=QuestionKind.LONG_TEXT, required=True),
    ]
    composed = await compose_answers(questions, PROFILE, {}, JOB, flaky)
    assert calls["n"] == 2
    assert all("generation failed" in c.gap_reason for c in composed)
