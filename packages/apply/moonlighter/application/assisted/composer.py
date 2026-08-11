"""Answer each question, and say plainly when it cannot be answered.

The rule that separates this from the automation it replaces: a question with no
defensible answer becomes a visible gap. Never an invented answer, never silence.
"""

import logging
from dataclasses import dataclass
from typing import Any

from moonlighter.application.answers.cv import CVNotFoundError, resolve_cv_path
from moonlighter.application.answers.field_map import pre_populate_answers
from moonlighter.application.answers.option_matcher import match_option_locally
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.core.llm import LLMCaller
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

Answer with the answer text only. No preamble, no explanation, no quotes.
If the profile gives you no basis to answer, reply with exactly: UNKNOWN
"""


@dataclass(frozen=True)
class ComposedAnswer:
    question: FormQuestion
    answer: str | None
    gap_reason: str | None

    def __post_init__(self) -> None:
        if (self.answer is None) == (self.gap_reason is None):
            raise ValueError("a composed answer is either answered or a gap, never both or neither")


async def _generate(
    question: FormQuestion, profile: dict[str, Any], job: dict[str, Any], llm_caller: LLMCaller
) -> str | None:
    constraint = ""
    if question.is_choice:
        options = "\n".join(f"- {o}" for o in question.options)
        constraint = f"Reply with exactly one of these options, copied verbatim:\n{options}"
    prompt = PROMPT.format(
        profile=wrap_untrusted("profile", str(profile), cap=6000),
        job=wrap_untrusted("job", str(job.get("description") or job), cap=6000),
        label=question.label,
        constraint=constraint,
    )
    try:
        raw = await llm_caller(prompt, "claude-sonnet-4-6")
    except Exception:
        logger.warning("could not generate an answer for %r", question.label)
        return None
    answer = raw.strip()
    return None if not answer or answer == "UNKNOWN" else answer


async def compose_answers(
    questions: list[FormQuestion],
    profile: dict[str, Any],
    config: dict[str, Any],
    job: dict[str, Any],
    llm_caller: LLMCaller,
) -> list[ComposedAnswer]:
    known = pre_populate_answers(
        [q.label for q in questions],
        profile,
        config,
        job.get("location"),
        job.get("remote_type"),
    )

    composed: list[ComposedAnswer] = []
    for question in questions:
        if question.kind is QuestionKind.FILE:
            # A file cannot be pasted, but naming the exact file to attach turns a
            # dead end into an instruction.
            try:
                path = resolve_cv_path(str(job.get("company") or ""), config)
                reason = f"upload this file yourself: {path}"
            except CVNotFoundError:
                reason = "upload a file yourself — no CV is configured"
            composed.append(ComposedAnswer(question, None, reason))
            continue

        answer = known.get(question.label) or await _generate(question, profile, job, llm_caller)

        if answer is None:
            composed.append(ComposedAnswer(question, None, "no basis in your profile to answer"))
            continue

        if question.is_choice:
            picked = match_option_locally(answer, list(question.options))
            if picked is None:
                composed.append(
                    ComposedAnswer(question, None, "no offered option matches — pick one yourself")
                )
                continue
            answer = picked

        composed.append(ComposedAnswer(question, answer, None))
    return composed
