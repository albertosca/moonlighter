"""Answer each question, and say plainly when it cannot be answered.

The rule that separates this from the automation it replaces: a question with no
defensible answer becomes a visible gap. Never an invented answer, never silence.
"""

from typing import Any

from moonlighter.application.answers.matching.field_map import pre_populate_answers
from moonlighter.application.answers.rules.compliance import is_compliance_question
from moonlighter.application.assisted.answer_screening import screen_answer
from moonlighter.application.assisted.answer_sources import AnswerSources
from moonlighter.application.assisted.composed_answer import ComposedAnswer
from moonlighter.application.assisted.file_gaps import file_gap_reason
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.core.llm.caller import LLMCaller


async def compose_answers(  # noqa: PLR0913, PLR0917 - public entry point called with this shape by service.py and the whole test suite
    questions: list[FormQuestion],
    profile: dict[str, Any],
    config: dict[str, Any],
    job: dict[str, Any],
    llm_caller: LLMCaller,
    *,
    job_cache: dict[str, Any] | None = None,
    answer_bank: dict[str, str] | None = None,
) -> list[ComposedAnswer]:
    """One answer or one gap per question, in order; each question waits for the previous one."""
    if job_cache is None:
        job_cache = {}
    if answer_bank is None:
        answer_bank = {}
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
        llm_caller=llm_caller,
        known=known,
        job_cache=job_cache,
        answer_bank=answer_bank,
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
