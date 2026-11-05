"""Pins the demographic and references guard, and its configured-demographics carve-out."""

import pytest

from moonlighter.application.assisted.composition.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from tests.application.assisted.composition.composer.sample_inputs import JOB, PROFILE, never_called


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
    # demographics block holds a value, demographics.py answers it deterministically —
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
    ("label", "would_leak"),
    [
        ("Describe how you would debug a race condition in a concurrent system", "White"),
        ("How would you improve our gender-neutral onboarding copy?", "Male"),
        ("Tell us about your work on accessibility for users with disabilities", "No"),
        ("Professional references (name, email, LinkedIn)", "https://linkedin.com/in/alberto"),
    ],
)
@pytest.mark.asyncio
async def test_a_question_that_merely_mentions_a_sensitive_word_is_not_answered(label, would_leak):
    # CANARY, all four measured live on 2026-09-11 against a first version of this
    # reorder: letting `known` outrank the guard handed the bypass to every rule in
    # _RULES, not just the five EEO ones — and those five were unanchored substring
    # matches. A race-condition engineering question came back answered "White", and
    # a references label came back answered with the LinkedIn URL, both with
    # gap_reason None, which makes the sheet print "nothing left for you but to
    # paste and submit". The carve-out must be scoped to real EEO questions.
    #
    # Two details make this canary actually bite, both found by measuring rather than
    # reasoning. SINGLE_SELECT, not LONG_TEXT: at LONG_TEXT the is_choice condition
    # blocks these on its own, so the test stayed green with the anchoring removed.
    # And `would_leak` must be among the options: with options that exclude it, the
    # value leaks out of the guard and is then filtered by option matching, which
    # produces a gap for an unrelated reason and hides the regression again.
    profile = {
        **PROFILE,
        "linkedin": "https://linkedin.com/in/alberto",
        "demographics": {"gender": "Male", "race": "White", "disability_status": "No"},
    }
    question = FormQuestion(
        label=label,
        kind=QuestionKind.SINGLE_SELECT,
        required=True,
        options=(would_leak, "Something else"),
    )
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
    # The privacy chain this rests on: a configured demographic is answered inside
    # the is_sensitive_label guard, which never sets is_llm_generated — and that
    # flag is the only thing that writes to job_cache. So the value cannot reach
    # form_data, and therefore cannot reach promote_application or the shared
    # cross-job bank. The chain is otherwise implicit in one boolean: if the
    # carve-out ever set that flag, or caching ever widened past it, demographics
    # would silently start crossing companies. This test is what would go red.
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
    # References are third-party data with no static_rules.py rule by design, so they
    # stay a gap regardless of what the demographics block holds.
    question = FormQuestion(label="References", kind=QuestionKind.LONG_TEXT, required=True)
    composed = await compose_answers([question], PROFILE_WITH_DEMOGRAPHICS, {}, JOB, never_called)
    assert composed[0].answer is None
    assert "demographic" in composed[0].gap_reason
