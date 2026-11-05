"""Pins the exact prompt, model and call shape the composer sends to the LLM."""

import logging
import re

import pytest
from moonlighter.application.assisted.composition.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

from tests.application.assisted.composition.composer.sample_inputs import JOB, PROFILE

EXPECTED_CHOICE_PROMPT = """Answer one question on a job application, as the candidate.

Candidate profile:
<profile_NONCE>
{}
</profile_NONCE>

Job:
<job_NONCE>
...
</job_NONCE>

Question: Which team appeals to you most?
Reply with exactly one of these options, copied verbatim:
- Platform
- Product
Pick the strongest option the profile supports: when the profile states the fact plainly \
(a language listed as fluent, a technology used in production), do not choose a weaker \
option than the fact warrants.

Write the answer in the same language as the job posting above. If the posting is in
Portuguese, answer in Portuguese; if in English, answer in English. Do not translate
the posting's language into your own.

You are answering AS the candidate, in the first person. Never write notes,
instructions, or apologies addressed to whoever is operating this tool — text like
"the candidate should provide..." or "please supply before submitting" is not an
answer. If answering would require information you do not have, reply with exactly:
UNKNOWN

Answer with the answer text only. No preamble, no explanation, no quotes.
If the profile gives you no basis to answer, reply with exactly: UNKNOWN
"""


def without_nonces(prompt: str) -> str:
    return re.sub(r"<(/?)(profile|job)_[0-9a-f]{8}>", r"<\1\2_NONCE>", prompt)


class RecordingCaller:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def __call__(self, *positional: object, **keywords: object) -> str:
        self.calls.append((positional, keywords))
        return self.reply

    @property
    def prompt(self) -> str:
        return str(self.calls[0][0][0])


@pytest.mark.asyncio
async def test_a_choice_question_sends_the_whole_prompt_byte_for_byte():
    question = FormQuestion(
        label="Which team appeals to you most?",
        kind=QuestionKind.SINGLE_SELECT,
        required=True,
        options=("Platform", "Product"),
    )
    caller = RecordingCaller("Product")
    await compose_answers([question], PROFILE, {}, JOB, caller)
    assert without_nonces(caller.prompt) == EXPECTED_CHOICE_PROMPT


@pytest.mark.asyncio
async def test_the_llm_is_called_with_the_prompt_and_the_model_name_only():
    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    caller = RecordingCaller("An answer.")
    await compose_answers([question], PROFILE, {}, JOB, caller)
    positional, keywords = caller.calls[0]
    assert positional[1:] == ("claude-sonnet-4-6",)
    assert len(positional) == 2
    assert keywords == {}


@pytest.mark.asyncio
async def test_a_text_question_leaves_the_constraint_line_empty():
    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    caller = RecordingCaller("An answer.")
    await compose_answers([question], PROFILE, {}, JOB, caller)
    assert "\nQuestion: Why us?\n\n\nWrite the answer in the same language" in caller.prompt


@pytest.mark.asyncio
async def test_a_multi_select_constraint_asks_for_one_or_more_lines():
    question = FormQuestion(
        label="Which of these do you know?",
        kind=QuestionKind.MULTI_SELECT,
        required=True,
        options=("Ruby", "Elixir"),
    )
    caller = RecordingCaller("Ruby")
    await compose_answers([question], PROFILE, {}, JOB, caller)
    assert (
        "\nReply with one or more of these options, one per line, copied verbatim:\n"
        "- Ruby\n- Elixir\nPick the strongest option"
    ) in caller.prompt


@pytest.mark.asyncio
async def test_a_job_without_a_description_puts_the_whole_job_into_the_prompt():
    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    caller = RecordingCaller("An answer.")
    await compose_answers([question], PROFILE, {}, {"company": "acme", "id": 3}, caller)
    assert "\nJob:\n<job_NONCE>\n{'company': 'acme', 'id': 3}\n</job_NONCE>\n" in without_nonces(
        caller.prompt
    )


@pytest.mark.asyncio
async def test_the_profile_and_the_job_are_each_capped_at_6000_characters():
    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    caller = RecordingCaller("An answer.")
    profile = {"summary": "y" * 7000}
    await compose_answers([question], profile, {}, {"description": "x" * 7000}, caller)
    prompt = without_nonces(caller.prompt)
    profile_block = prompt.split("<profile_NONCE>\n")[1].split("\n</profile_NONCE>")[0]
    job_block = prompt.split("<job_NONCE>\n")[1].split("\n</job_NONCE>")[0]
    assert len(profile_block) == 6000
    assert profile_block.startswith("{'summary': 'yyy")
    assert job_block == "x" * 6000


@pytest.mark.asyncio
async def test_a_failed_generation_logs_one_warning_naming_the_question(caplog):
    async def explodes(prompt: str, model: str) -> str:
        raise RuntimeError("backend exploded")

    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)
    with caplog.at_level(logging.WARNING):
        await compose_answers([question], PROFILE, {}, JOB, explodes)
    messages = [
        (record.levelno, record.getMessage())
        for record in caplog.records
        if record.getMessage().startswith("could not generate")
    ]
    assert messages == [(logging.WARNING, "could not generate an answer for 'Why us?'")]
