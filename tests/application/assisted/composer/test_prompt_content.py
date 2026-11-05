"""Pins what reaches the prompt: the posting, the curated profile and the choice instructions."""

import pytest
from moonlighter.application.assisted.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

from tests.application.assisted.composer.sample_inputs import JOB, PROFILE


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


@pytest.mark.asyncio
async def test_llm_prompt_carries_only_the_curated_profile():
    """The references (a third party's contacts), preferences (the salary figure — E2)
    and demographics must never reach the prompt; the old applier path curated
    them out and the composer must too.
    """
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
async def test_a_choice_prompt_tells_the_model_not_to_underclaim():
    """The model picked "minor limitations" for a profile that says English
    (fluent/native) — live on the Nubank shadow-run (2026-08-13), with the fact
    present in the curated prompt. The choice constraint must instruct it to
    pick the strongest option the profile supports.
    """
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
