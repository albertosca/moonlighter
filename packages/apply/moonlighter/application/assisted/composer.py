"""Answer each question, and say plainly when it cannot be answered.

The rule that separates this from the automation it replaces: a question with no
defensible answer becomes a visible gap. Never an invented answer, never silence.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

from moonlighter.application.answers.compliance import is_compliance_question
from moonlighter.application.answers.cv import CVNotFoundError, resolve_cv_path
from moonlighter.application.answers.field_map import pre_populate_answers
from moonlighter.application.answers.option_matcher import match_option_locally
from moonlighter.application.answers.profile import profile_for_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.core.config import NEEDS_REVIEW_SENTINEL
from moonlighter.core.llm import LLMCaller, is_spend_limit
from moonlighter.core.parsing import wrap_untrusted

logger = logging.getLogger(__name__)

# File fields whose label asks for a CV/resume — the only ones whose gap should
# name the configured CV as the file to attach.
_CV_LABEL = re.compile(r"\bcv\b|resume|curr[ií]c", re.I)

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

# Markers of prose addressed to the tool's operator instead of the employer.
# Provenance: two live incidents — a references answer (2026-08-04) and an
# address answer (2026-08-05) written ABOUT the candidate in the third person,
# instructing whoever drives the tool. A prompt-only fix failed twice; this
# guard is deterministic. False positives are acceptable by construction: the
# failure direction is a human answering one more question by hand.
_OPERATOR_MARKERS = (
    "the candidate",
    "the applicant",
    "cannot attach",
    "unable to attach",
    "please supply",
    "please provide",
    "please upload",
    "material provided",
    "before submitting",
    "note to",
)


def _operator_directed(answer: str) -> str | None:
    """The first operator-directed marker found in the answer, or None."""
    lowered = answer.lower()
    for marker in _OPERATOR_MARKERS:
        if marker in lowered:
            return marker
    return None


@dataclass(frozen=True)
class ComposedAnswer:
    question: FormQuestion
    answer: str | None
    gap_reason: str | None

    def __post_init__(self) -> None:
        if (self.answer is None) == (self.gap_reason is None):
            raise ValueError("a composed answer is either answered or a gap, never both or neither")


_SPEND_LIMIT_REASON = "the LLM spend limit was hit — generation aborted, answer this yourself"


class _GenerationError(Exception):
    """The LLM call itself failed (spend limit, network, backend outage, ...).

    Distinct on purpose from a plain UNKNOWN: UNKNOWN means the profile gives
    no basis to answer, which is a fact about the candidate. This means the
    attempt to answer never completed, which is a fact about the tool run.
    Conflating the two put "answer generation failed" and "no basis in your
    profile to answer" behind the same gap reason, which reads as a
    knowledge gap even when a spend-limit or network error is the real cause.
    """


async def _generate(
    question: FormQuestion, profile: dict[str, Any], job: dict[str, Any], llm_caller: LLMCaller
) -> str | None:
    constraint = ""
    if question.is_choice:
        options = "\n".join(f"- {o}" for o in question.options)
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
        constraint = (
            f"Reply with {how_many}, copied verbatim:\n{options}\n"
            "Pick the strongest option the profile supports: when the profile states "
            "the fact plainly (a language listed as fluent, a technology used in "
            "production), do not choose a weaker option than the fact warrants."
        )
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
    except Exception as e:
        logger.warning("could not generate an answer for %r", question.label)
        raise _GenerationError(str(e)) from e
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
    llm_exhausted = False
    for question in questions:
        if question.kind is QuestionKind.FILE:
            # A file cannot be pasted, but naming the exact file to attach turns a
            # dead end into an instruction — only for CV-shaped labels: a "Cover
            # letter" gap naming the CV instructs the operator to attach the
            # wrong document (found on the GitLab gate sheet, 2026-08-13).
            if _CV_LABEL.search(question.label):
                try:
                    path = resolve_cv_path(str(job.get("company") or ""), config)
                    reason = f"upload this file yourself: {path}"
                except CVNotFoundError:
                    reason = "upload a file yourself — no CV is configured"
            else:
                reason = "upload a file yourself"
            composed.append(ComposedAnswer(question, None, reason))
            continue

        if is_compliance_question(question.label, question.options):
            # Declaration/conflict-of-interest questions are never answered by
            # the machine — live 2026-08-21 (gympass #3416): the model signed a
            # false public-body affiliation. Same deterministic category as
            # references, salary and demographics; guarded before `known` so no
            # accidental label collision can pre-populate a declaration either.
            composed.append(
                ComposedAnswer(
                    question,
                    None,
                    "declaration/compliance question — answer this yourself",
                )
            )
            continue

        answer: str | None
        if question.label in known:
            # Presence, not truthiness: known can legitimately map a label to ""
            # (_salary_expectation with no salary_target configured, by design —
            # E2 forbids letting the figure fall through to the LLM). `known.get(...)
            # or ...` treated that deliberate "" the same as absence and asked the
            # LLM to invent a number anyway.
            value = known[question.label]
            if value == "":
                composed.append(
                    ComposedAnswer(
                        question,
                        None,
                        "no configured value for this field — answer this yourself",
                    )
                )
                continue
            answer = value
        else:
            if llm_exhausted:
                composed.append(ComposedAnswer(question, None, _SPEND_LIMIT_REASON))
                continue
            try:
                answer = await _generate(question, profile, job, llm_caller)
            except _GenerationError as e:
                # After a spend-limit failure every further call is doomed the
                # same way — one gap per remaining generated answer, no more
                # calls. Deterministic pre-population above is unaffected.
                cause = e.__cause__
                if isinstance(cause, Exception) and is_spend_limit(cause):
                    llm_exhausted = True
                    composed.append(ComposedAnswer(question, None, _SPEND_LIMIT_REASON))
                else:
                    composed.append(
                        ComposedAnswer(
                            question, None, "answer generation failed — answer this yourself"
                        )
                    )
                continue

        # pre_populate_answers can hand back its own review sentinel instead of a real
        # value (work-authorization/sponsorship fields when the country can't be inferred;
        # salary fields when the units disagree) — for ANY question kind, not just choices.
        # Screened unconditionally, before is_choice, so it never reaches a TEXT/LONG_TEXT
        # field as a literal "__NEEDS_REVIEW__" answer pasted into a real form.
        if answer == NEEDS_REVIEW_SENTINEL:
            composed.append(
                ComposedAnswer(question, None, "no defensible answer here — answer this yourself")
            )
            continue

        if answer is None:
            composed.append(ComposedAnswer(question, None, "no basis in your profile to answer"))
            continue

        if not question.is_choice and (marker := _operator_directed(answer)) is not None:
            composed.append(
                ComposedAnswer(
                    question,
                    None,
                    f'the model addressed the operator ("{marker}...") — answer this yourself',
                )
            )
            continue

        if question.kind is QuestionKind.MULTI_SELECT:
            picks: list[str] = []
            for part in re.split(r"[\n,]+", answer):
                matched = match_option_locally(part.strip(), list(question.options))
                if matched and matched not in picks:
                    picks.append(matched)
            if not picks:
                composed.append(
                    ComposedAnswer(question, None, "no offered option matches — pick yourself")
                )
                continue
            answer = "\n".join(picks)
        elif question.is_choice:
            picked = match_option_locally(answer, list(question.options))
            if picked is None:
                composed.append(
                    ComposedAnswer(question, None, "no offered option matches — pick one yourself")
                )
                continue
            answer = picked

        composed.append(ComposedAnswer(question, answer, None))
    return composed
