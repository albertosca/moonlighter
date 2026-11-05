"""Pins the per-job answer cache (Layer A): what it serves, what it stores, and what it never shadows."""

import pytest
from moonlighter.application.assisted.composition.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

from tests.application.assisted.composition.composer.sample_inputs import (
    JOB,
    PROFILE,
    answers_anything,
    never_called,
)


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
