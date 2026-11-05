"""Pins how select answers are matched to the offered options, and the option-count limit."""

import pytest
from moonlighter.application.assisted.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

from tests.application.assisted.composer.sample_inputs import JOB, PROFILE


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


def _select_with(option_count: int) -> FormQuestion:
    # The label avoids every pre_populate_answers rule (country, location, ...) so
    # the question would otherwise reach the LLM.
    return FormQuestion(
        label="Which office would you join?",
        kind=QuestionKind.SINGLE_SELECT,
        required=True,
        options=tuple(f"Office {number}" for number in range(1, option_count + 1)),
    )


@pytest.mark.asyncio
async def test_a_choice_with_more_than_200_options_is_a_gap_without_the_llm():
    # A Lever select of 3,301 options put ~26k tokens of option list into one prompt.
    prompts = []

    async def records_the_call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        prompts.append(prompt)
        return "Office 1"

    composed = await compose_answers([_select_with(201)], PROFILE, {}, JOB, records_the_call)
    assert prompts == []
    assert composed[0].answer is None
    assert composed[0].gap_reason == "pick your answer from the 201 options on the form"


@pytest.mark.asyncio
async def test_a_choice_with_200_options_still_goes_to_the_llm():
    prompts = []

    async def picks_the_last(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        prompts.append(prompt)
        return "Office 200"

    composed = await compose_answers([_select_with(200)], PROFILE, {}, JOB, picks_the_last)
    assert len(prompts) == 1
    assert composed[0].answer == "Office 200"
