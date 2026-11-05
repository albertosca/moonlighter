"""Pins the order of the composer's stages and the state it carries from one question to the next."""

import pytest

from moonlighter.application.assisted.composition import composer
from moonlighter.application.assisted.composition.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from tests.application.assisted.composition.composer.sample_inputs import JOB, PROFILE, never_called

COMPLIANCE_OPTIONS = (
    (
        "I currently hold or have previously held a position, role, or affiliation "
        "with a public body, government entity, state-owned enterprise, political "
        "party, or international organization."
    ),
    "I have nothing to declare.",
)
TEAM_SELECT = FormQuestion(
    label="Which team appeals to you most?",
    kind=QuestionKind.SINGLE_SELECT,
    required=True,
    options=("Platform", "Product"),
)


@pytest.mark.asyncio
async def test_a_file_question_is_a_file_gap_before_the_compliance_check():
    question = FormQuestion(
        label="Conflict of Interest Declaration", kind=QuestionKind.FILE, required=True
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].gap_reason == "upload a file yourself"


@pytest.mark.asyncio
async def test_the_compliance_check_runs_before_the_sensitive_label_guard():
    question = FormQuestion(
        label="Gender", kind=QuestionKind.MULTI_SELECT, required=True, options=COMPLIANCE_OPTIONS
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, never_called)
    assert composed[0].gap_reason == "declaration/compliance question — answer this yourself"


@pytest.mark.asyncio
async def test_the_option_limit_gap_comes_before_the_spend_limit_gap():
    async def spent(prompt: str, model: str) -> str:
        raise RuntimeError("Claude AI usage spend limit reached")

    huge_select = FormQuestion(
        label="Which office would you join?",
        kind=QuestionKind.SINGLE_SELECT,
        required=True,
        options=tuple(f"Office {number}" for number in range(1, 202)),
    )
    first = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    composed = await compose_answers([first, huge_select], PROFILE, {}, JOB, spent)
    assert "spend limit" in composed[0].gap_reason
    assert composed[1].gap_reason == "pick your answer from the 201 options on the form"


@pytest.mark.asyncio
async def test_the_job_cache_is_read_before_the_answer_bank():
    question = FormQuestion(
        label="Do you have 5+ years of Python experience?",
        kind=QuestionKind.BOOLEAN,
        required=True,
    )
    job_cache = {question.label: {"answer": "From the cache", "kind": "boolean"}}
    bank = {"do you have 5+ years of python experience": "From the bank"}
    composed = await compose_answers(
        [question], PROFILE, {}, JOB, never_called, job_cache=job_cache, answer_bank=bank
    )
    assert composed[0].answer == "From the cache"


@pytest.mark.asyncio
async def test_the_job_cache_stores_the_matched_option_and_serves_a_repeated_label():
    calls: list[str] = []

    async def lowercase_pick(prompt: str, model: str) -> str:
        calls.append(prompt)
        return "product"

    job_cache: dict[str, dict[str, str]] = {}
    composed = await compose_answers(
        [TEAM_SELECT, TEAM_SELECT], PROFILE, {}, JOB, lowercase_pick, job_cache=job_cache
    )
    assert job_cache == {TEAM_SELECT.label: {"answer": "Product", "kind": "single_select"}}
    assert len(calls) == 1
    assert [item.answer for item in composed] == ["Product", "Product"]


@pytest.mark.asyncio
async def test_the_operator_guard_also_screens_known_cached_and_banked_answers():
    note = "please provide a link"
    known = FormQuestion(label="Website", kind=QuestionKind.TEXT, required=True)
    cached = FormQuestion(label="Portfolio walkthrough", kind=QuestionKind.TEXT, required=True)
    banked = FormQuestion(label="Anything else to add?", kind=QuestionKind.TEXT, required=True)
    composed = await compose_answers(
        [known, cached, banked],
        {**PROFILE, "website": note},
        {},
        JOB,
        never_called,
        job_cache={cached.label: {"answer": note, "kind": "text"}},
        answer_bank={"anything else to add": note},
    )
    expected = 'the model addressed the operator ("please provide...") — answer this yourself'
    assert [item.gap_reason for item in composed] == [expected, expected, expected]


@pytest.mark.asyncio
async def test_a_comma_inside_a_multi_select_reply_splits_it():
    async def replies_with_a_comma(prompt: str, model: str) -> str:
        return "Ruby, Rails"

    question = FormQuestion(
        label="Which of these do you know?",
        kind=QuestionKind.MULTI_SELECT,
        required=True,
        options=("Ruby, Rails", "Rails"),
    )
    composed = await compose_answers([question], PROFILE, {}, JOB, replies_with_a_comma)
    assert composed[0].answer == "Ruby, Rails\nRails"


@pytest.mark.parametrize("include_questions", [True, False])
@pytest.mark.asyncio
async def test_pre_population_runs_once_over_every_label(monkeypatch, include_questions):
    real_pre_populate = composer.pre_populate_answers
    calls: list[list[str]] = []

    def spy(labels, *rest, **keywords):
        calls.append(list(labels))
        return real_pre_populate(labels, *rest, **keywords)

    monkeypatch.setattr(composer, "pre_populate_answers", spy)
    questions = [
        FormQuestion(label="Resume/CV", kind=QuestionKind.FILE, required=True),
        FormQuestion(label="First Name", kind=QuestionKind.TEXT, required=True),
    ]
    if not include_questions:
        questions = []
    await compose_answers(questions, PROFILE, {}, JOB, never_called)
    assert calls == [[question.label for question in questions]]
