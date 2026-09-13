import subprocess
import sys

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
async def test_a_cv_file_gap_names_the_tailored_pdf_with_review_instruction(tmp_path):
    tailored = tmp_path / "7"
    tailored.mkdir()
    cv = tailored / "cv.pdf"
    cv.write_bytes(b"%PDF-1.5\n...\n%%EOF\n")  # real-shaped: resolve_cv_path sniffs it
    question = FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True)
    job = {**JOB, "id": 7}
    composed = await compose_answers(
        [question], PROFILE, {"cv": {"generated_dir": str(tmp_path)}}, job, answers_anything
    )
    assert str(cv) in composed[0].gap_reason
    assert "tailored for this job — review it before uploading" in composed[0].gap_reason


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
    failures that actually happened.

    The label is deliberately neutral: what this canary pins is the ANSWER TEXT
    reaching the operator-directed guard, and the original "References" label is
    now intercepted upstream by is_sensitive_label — which would leave this
    passing without the operator guard ever running."""

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


GYMPASS_CONFLICT_OPTIONS = (
    "I currently hold or have previously held a position, role, or affiliation "
    "with a public body, government entity, state-owned enterprise, political "
    "party, or international organization.",
    "I engage in external professional activity.",
    "I have nothing to declare.",
)


@pytest.mark.asyncio
async def test_a_compliance_declaration_never_reaches_the_llm():
    # Live incident 2026-08-21 (gympass #3416): the model picked the public-body
    # affiliation option for a candidate who never held one — a signed false
    # statement. Declaration questions are deterministic-guard territory.
    question = FormQuestion(
        label="Conflict of Interest Declaration",
        kind=QuestionKind.MULTI_SELECT,
        required=True,
        options=GYMPASS_CONFLICT_OPTIONS,
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].answer is None
    assert "compliance" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_compliance_detected_by_options_under_a_neutral_label():
    question = FormQuestion(
        label="Please select all that apply",
        kind=QuestionKind.MULTI_SELECT,
        required=True,
        options=GYMPASS_CONFLICT_OPTIONS,
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].answer is None
    assert "compliance" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_text_certification_question_is_also_guarded():
    question = FormQuestion(
        label="I certify that the information provided is true and complete",
        kind=QuestionKind.TEXT,
        required=True,
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].answer is None
    assert "compliance" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_demographic_question_never_reaches_the_llm():
    # profile_for_answers already keeps demographic DATA out of the prompt, but
    # nothing stopped the model from being ASKED a demographic-shaped question
    # and hallucinating an answer anyway — same deterministic-guard category as
    # compliance declarations above.
    question = FormQuestion(
        label="Gender", kind=QuestionKind.SINGLE_SELECT, required=True, options=("Male", "Female")
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].answer is None
    assert "demographic" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_references_question_never_reaches_the_llm():
    question = FormQuestion(label="References", kind=QuestionKind.LONG_TEXT, required=True)
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].answer is None
    assert "demographic" in composed[0].gap_reason


PROFILE_WITH_DEMOGRAPHICS = {
    **PROFILE,
    "demographics": {"gender": "Male", "race": "White", "veteran_status": "No"},
}


@pytest.mark.asyncio
async def test_a_configured_demographic_value_answers_instead_of_gapping():
    # The guard exists to stop the MODEL from inventing an answer, not to stop
    # Alberto's own configured answer from being used. When profile.yaml's
    # demographics block holds a value, field_map answers it deterministically —
    # never_called proves this is not the LLM doing it.
    question = FormQuestion(
        label="Gender", kind=QuestionKind.SINGLE_SELECT, required=True, options=("Male", "Female")
    )
    composed = await compose_answers([question], PROFILE_WITH_DEMOGRAPHICS, {}, JOB, never_called)
    assert composed[0].answer == "Male"
    assert composed[0].gap_reason is None


@pytest.mark.asyncio
async def test_an_unconfigured_demographic_still_gaps_even_with_a_demographics_block():
    # A demographics block that simply lacks THIS key must behave like no block at
    # all: the guard fires, the LLM is never consulted. Pins the distinction the
    # whole reorder rests on — "configured" means this key, not the block.
    question = FormQuestion(
        label="Disability status",
        kind=QuestionKind.SINGLE_SELECT,
        required=True,
        options=("Yes", "No"),
    )
    composed = await compose_answers([question], PROFILE_WITH_DEMOGRAPHICS, {}, JOB, never_called)
    assert composed[0].answer is None
    assert "demographic" in composed[0].gap_reason


@pytest.mark.parametrize(
    "label",
    [
        "Describe how you would debug a race condition in a concurrent system",
        "How would you improve our gender-neutral onboarding copy?",
        "Tell us about your work on accessibility for users with disabilities",
        "Professional references (name, email, LinkedIn)",
    ],
)
@pytest.mark.asyncio
async def test_a_free_text_question_that_merely_mentions_a_sensitive_word_is_not_answered(label):
    # CANARY, all four measured live on 2026-09-11 against a first version of this
    # reorder: letting `known` outrank the guard handed the bypass to every rule in
    # _RULES, not just the five EEO ones — and those five were unanchored substring
    # matches. A race-condition engineering question came back answered "White", and
    # a references label came back answered with the LinkedIn URL, both with
    # gap_reason None, which makes the sheet print "nothing left for you but to
    # paste and submit". The carve-out must be scoped to real EEO questions.
    profile = {
        **PROFILE,
        "linkedin": "https://linkedin.com/in/alberto",
        "demographics": {"gender": "Male", "race": "White", "disability_status": "No"},
    }
    question = FormQuestion(label=label, kind=QuestionKind.LONG_TEXT, required=True)
    composed = await compose_answers([question], profile, {}, JOB, never_called)
    assert composed[0].answer is None
    assert composed[0].gap_reason is not None


@pytest.mark.asyncio
async def test_a_demographic_label_asked_as_free_text_is_not_answered():
    # Real EEO self-identification is always a select. A free-text field whose label
    # happens to be exactly "Gender" is far more likely to be something else, so the
    # carve-out requires a choice kind.
    question = FormQuestion(label="Gender", kind=QuestionKind.LONG_TEXT, required=True)
    composed = await compose_answers([question], PROFILE_WITH_DEMOGRAPHICS, {}, JOB, never_called)
    assert composed[0].answer is None
    assert "demographic" in composed[0].gap_reason


@pytest.mark.asyncio
async def test_a_configured_demographic_answer_is_never_written_to_the_job_cache():
    # The privacy chain the reorder now rests on: a configured demographic is
    # answered via `known`, and `known` answers are never cached (only
    # is_llm_generated ones are), so it can never be promoted into the shared
    # cross-job bank by update_status. That chain is otherwise implicit in a
    # flag — if caching ever widened to `known`, demographics would silently
    # start crossing companies. This test is what would go red.
    question = FormQuestion(
        label="Gender", kind=QuestionKind.SINGLE_SELECT, required=True, options=("Male", "Female")
    )
    job_cache: dict[str, dict[str, str]] = {}
    composed = await compose_answers(
        [question], PROFILE_WITH_DEMOGRAPHICS, {}, JOB, never_called, job_cache=job_cache
    )
    assert composed[0].answer == "Male"
    assert job_cache == {}


@pytest.mark.asyncio
async def test_references_gap_even_when_demographics_are_configured():
    # References are third-party data with no field_map rule by design, so they
    # stay a gap regardless of what the demographics block holds.
    question = FormQuestion(label="References", kind=QuestionKind.LONG_TEXT, required=True)
    composed = await compose_answers([question], PROFILE_WITH_DEMOGRAPHICS, {}, JOB, never_called)
    assert composed[0].answer is None
    assert "demographic" in composed[0].gap_reason


# ── job_cache (Layer A: per-job cache) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_a_job_cache_hit_skips_the_llm():
    question = FormQuestion(
        label="Describe a challenge you overcame", kind=QuestionKind.TEXT, required=True
    )
    job_cache = {"Describe a challenge you overcame": {"answer": "cached answer", "kind": "text"}}
    composed = await compose_answers(
        [question], PROFILE, {}, JOB, never_called, job_cache=job_cache
    )
    assert composed[0].answer == "cached answer"


@pytest.mark.asyncio
async def test_a_new_llm_answer_is_written_into_the_job_cache():
    question = FormQuestion(
        label="Describe a challenge you overcame", kind=QuestionKind.TEXT, required=True
    )
    job_cache: dict[str, dict[str, str]] = {}
    await compose_answers([question], PROFILE, {}, JOB, answers_anything, job_cache=job_cache)
    assert job_cache["Describe a challenge you overcame"] == {
        "answer": "a generated answer",
        "kind": "text",
    }


@pytest.mark.asyncio
async def test_a_gap_is_not_written_into_the_job_cache():
    question = FormQuestion(
        label="Describe a challenge you overcame", kind=QuestionKind.TEXT, required=True
    )

    async def unknown(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return "UNKNOWN"

    job_cache: dict[str, dict[str, str]] = {}
    composed = await compose_answers([question], PROFILE, {}, JOB, unknown, job_cache=job_cache)
    assert composed[0].answer is None
    assert job_cache == {}


@pytest.mark.asyncio
async def test_an_operator_directed_answer_is_not_written_into_the_job_cache():
    # Proves the cache write happens at the FINAL success point, not right after
    # the LLM call returns: an answer that later gets rejected as operator-directed
    # must never be replayed from the cache on a second call.
    # The label must NOT be one is_sensitive_label catches (this test used to say
    # "References", which the demographic/reference guard now intercepts before the
    # LLM is ever called — the assertions still passed, for the wrong reason).
    question = FormQuestion(label="Portfolio walkthrough", kind=QuestionKind.TEXT, required=True)

    async def operator_directed(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return "the candidate will provide a walkthrough later"

    job_cache: dict[str, dict[str, str]] = {}
    composed = await compose_answers(
        [question], PROFILE, {}, JOB, operator_directed, job_cache=job_cache
    )
    assert composed[0].answer is None
    assert "operator" in composed[0].gap_reason
    assert job_cache == {}


@pytest.mark.asyncio
async def test_a_known_field_is_never_overridden_by_the_job_cache_or_answer_bank():
    # pre_populate_answers (known) is checked before either cache — a label it
    # already resolves must never be shadowed by a stale/wrong cache entry.
    question = FormQuestion(label="First Name", kind=QuestionKind.TEXT, required=True)
    job_cache = {"First Name": {"answer": "WRONG", "kind": "text"}}
    bank = {"first name": "ALSO WRONG"}
    composed = await compose_answers(
        [question], PROFILE, {}, JOB, never_called, job_cache=job_cache, answer_bank=bank
    )
    assert composed[0].answer == "Alberto"


@pytest.mark.asyncio
async def test_a_legacy_flat_shaped_job_cache_entry_is_treated_as_a_miss():
    # Application.form_data predates this feature: 8 rows in the live DB still
    # hold the removed browser-automation tool's flat label->string shape.
    # Indexing one of those with ["answer"] raised
    # "TypeError: string indices must be integers" — and it raised BEFORE _sheet
    # could rewrite the column, so those jobs stayed permanently broken.
    label = "Do you have at least 8 years of professional experience?"
    question = FormQuestion(label=label, kind=QuestionKind.TEXT, required=True)
    job_cache = {label: "Yes, I have 10 years"}
    composed = await compose_answers(
        [question], PROFILE, {}, JOB, answers_anything, job_cache=job_cache
    )
    assert composed[0].answer == "a generated answer"


@pytest.mark.asyncio
async def test_an_empty_cached_answer_is_treated_as_a_miss():
    # Presence is not enough, same as `known`'s deliberate "" a few lines above:
    # a cached empty string is not an answer, and honouring it would paste a
    # blank into a real form instead of asking the LLM again.
    label = "Describe a challenge you overcame"
    question = FormQuestion(label=label, kind=QuestionKind.LONG_TEXT, required=True)
    job_cache = {label: {"answer": "", "kind": "long_text"}}
    composed = await compose_answers(
        [question], PROFILE, {}, JOB, answers_anything, job_cache=job_cache
    )
    assert composed[0].answer == "a generated answer"


# ── answer_bank (Layer B: cross-job bank) ────────────────────────────────────


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


def test_importing_the_composer_does_not_pull_in_the_db_layer():
    # The plan's Global Constraint: compose_answers does no DB access, directly
    # or via import. answer_bank.py imports AnswerBankEntry inside the two
    # functions that need it precisely so that importing this module — which
    # wants only the pure helpers — does not drag in peewee and the whole DB
    # layer. Checked in a subprocess: this pytest session imported both long ago.
    code = (
        "import sys, moonlighter.application.assisted.composer as _;"
        "print('peewee' in sys.modules, 'moonlighter.core.db' in sys.modules)"
    )
    out = subprocess.run(  # noqa: S603 - literal argv, this interpreter, no shell
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout
    assert out.strip() == "False False"
