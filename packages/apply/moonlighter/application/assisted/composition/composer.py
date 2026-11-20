"""Answer each question, and say plainly when it cannot be answered.

The rule that separates this from the automation it replaces: a question with no
defensible answer becomes a visible gap. Never an invented answer, never silence.
"""

from dataclasses import KW_ONLY, dataclass, field
from typing import Any

from moonlighter.application.answers.matching.field_map import pre_populate_answers
from moonlighter.application.answers.rules.compliance import is_compliance_question
from moonlighter.application.assisted.composition.answer_screening import screen_answer
from moonlighter.application.assisted.composition.answer_sources import AnswerSources
from moonlighter.application.assisted.composition.composed_answer import ComposedAnswer
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sheet.file_gaps import file_gap_reason
from moonlighter.core.llm.caller import LLMCaller


@dataclass(frozen=True)
class CompositionContext:
    """Everything compose_answers needs besides the questions.

    The two caches default to a fresh dict per context, and the composer writes
    new LLM answers into job_cache, so a caller that wants them back passes its own.
    """

    profile: dict[str, Any]
    config: dict[str, Any]
    job: dict[str, Any]
    llm_caller: LLMCaller
    _: KW_ONLY
    job_cache: dict[str, Any] = field(default_factory=dict)
    answer_bank: dict[str, str] = field(default_factory=dict)


async def compose_answers(
    questions: list[FormQuestion], context: CompositionContext
) -> list[ComposedAnswer]:
    """One answer or one gap per question, in order; each question waits for the previous one."""
    profile, config, job = context.profile, context.config, context.job
    known = pre_populate_answers(
        [question.label for question in questions],
        profile,
        config,
        job_location=job.get("location"),
        job_remote_type=job.get("remote_type"),
    )
    sources = AnswerSources(
        profile=profile,
        job=job,
        llm_caller=context.llm_caller,
        known=known,
        job_cache=context.job_cache,
        answer_bank=context.answer_bank,
    )
    return [await _compose_one(question, config, sources) for question in questions]


async def _compose_one(
    question: FormQuestion, config: dict[str, Any], sources: AnswerSources
) -> ComposedAnswer:
    if question.kind is QuestionKind.FILE:
        return ComposedAnswer(question, None, file_gap_reason(question, config, sources.job))

    if is_compliance_question(question.label, question.options):
        # Declaration/conflict-of-interest questions are never answered by
        # the machine — live 2026-08-21 (gympass #3416): the model signed a
        # false public-body affiliation. Same deterministic category as
        # references, salary and demographics; guarded before `known` so no
        # accidental label collision can pre-populate a declaration either.
        return ComposedAnswer(
            question, None, "declaration/compliance question — answer this yourself"
        )

    sourced = await sources.find(question)
    if isinstance(sourced, ComposedAnswer):
        return sourced
    composed = screen_answer(question, sourced.answer)
    if sourced.is_llm_generated and composed.answer is not None:
        sources.job_cache[question.label] = {"answer": composed.answer, "kind": question.kind.value}
    return composed
