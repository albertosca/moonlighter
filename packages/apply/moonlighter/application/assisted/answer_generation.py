"""Ask the model for one answer, from the curated profile and the posting."""

import logging
from typing import Any

from moonlighter.application.answers.profile import profile_for_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.parsing import wrap_untrusted

logger = logging.getLogger(__name__)

PROMPT = """Answer one question on a job application, as the candidate.

Candidate profile:
{profile}

Job:
{job}

Question: {label}
{constraint}

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


class GenerationError(Exception):
    """The LLM call itself failed (spend limit, network, backend outage, ...).

    Distinct on purpose from a plain UNKNOWN: UNKNOWN means the profile gives
    no basis to answer, which is a fact about the candidate. This means the
    attempt to answer never completed, which is a fact about the tool run.
    Conflating the two put "answer generation failed" and "no basis in your
    profile to answer" behind the same gap reason, which reads as a
    knowledge gap even when a spend-limit or network error is the real cause.
    """


def _choice_constraint(question: FormQuestion) -> str:
    """The prompt line that limits a choice question to its offered options."""
    options = "\n".join(f"- {option}" for option in question.options)
    # "Strongest the profile supports": the model picked "minor limitations"
    # for a profile saying English (fluent/native) — live, 2026-08-13 — with
    # the fact right there in the prompt. Hedging downward misrepresents the
    # candidate exactly like overclaiming does, just in the safer-feeling
    # direction.
    # A multi-select answered with a single pick under-claims structurally
    # ("which of these do you know?"); the model may take every option the
    # profile supports.
    how_many = (
        "one or more of these options, one per line"
        if question.kind is QuestionKind.MULTI_SELECT
        else "exactly one of these options"
    )
    return (
        f"Reply with {how_many}, copied verbatim:\n{options}\n"
        "Pick the strongest option the profile supports: when the profile states "
        "the fact plainly (a language listed as fluent, a technology used in "
        "production), do not choose a weaker option than the fact warrants."
    )


async def generate_answer(
    question: FormQuestion, profile: dict[str, Any], job: dict[str, Any], *, llm_caller: LLMCaller
) -> str | None:
    """The model's answer, or None for an empty or UNKNOWN reply; GenerationError if the call fails."""
    constraint = _choice_constraint(question) if question.is_choice else ""
    prompt = PROMPT.format(
        # Least privilege at the prompt boundary: references (third-party
        # contacts), preferences (the salary figure — E2) and demographics
        # never reach the model. Deterministic pre-population upstream still
        # uses the full profile; this curation is prompt-only.
        profile=wrap_untrusted("profile", str(profile_for_answers(profile)), cap=6000),
        job=wrap_untrusted("job", str(job.get("description") or job), cap=6000),
        label=question.label,
        constraint=constraint,
    )
    try:
        raw = await llm_caller(prompt, "claude-sonnet-4-6")
    except Exception as error:
        logger.warning("could not generate an answer for %r", question.label)
        raise GenerationError(str(error)) from error
    answer = raw.strip()
    return None if not answer or answer == "UNKNOWN" else answer
