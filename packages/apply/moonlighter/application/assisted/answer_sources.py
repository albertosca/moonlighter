"""Where a question's answer comes from: the profile, the job's cache, the bank, or the model.

Each source is tried in a fixed order, and a source that must not answer turns
the question into a gap on the spot instead of falling through to the next one.
"""

from dataclasses import dataclass
from typing import Any

from moonlighter.application.answers.bank_eligibility import (
    is_bank_eligible,
    is_sensitive_label,
    normalize_question,
)
from moonlighter.application.answers.field_map import demographic_answer
from moonlighter.application.assisted.answer_generation import GenerationError, generate_answer
from moonlighter.application.assisted.composed_answer import ComposedAnswer
from moonlighter.application.assisted.questions import FormQuestion
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.spend_limit import is_spend_limit

# A choice with more options than this never reaches the LLM: a Lever select of
# 3,301 options put ~26k tokens of option list into one prompt. The person picks
# from the form instead.
LLM_OPTION_LIMIT = 200

_SPEND_LIMIT_REASON = "the LLM spend limit was hit — generation aborted, answer this yourself"


@dataclass(frozen=True)
class SourcedAnswer:
    """An answer still to be screened, and whether the model wrote it (only those are cached)."""

    answer: str | None
    is_llm_generated: bool = False


@dataclass
class AnswerSources:
    """The sources for one form, and the spend-limit state carried from question to question."""

    profile: dict[str, Any]
    job: dict[str, Any]
    llm_caller: LLMCaller
    known: dict[str, str]
    job_cache: dict[str, Any]
    answer_bank: dict[str, str]
    llm_exhausted: bool = False

    async def find(self, question: FormQuestion) -> ComposedAnswer | SourcedAnswer:
        """The first source that settles the question: an answer to screen, or a gap."""
        if is_sensitive_label(question.label):
            # profile_for_answers keeps demographic/reference DATA out of the prompt,
            # but nothing stops the model from being ASKED a question shaped like one
            # and hallucinating an answer anyway — which would land on this job's
            # sheet and in its form_data. So the guard stays ABOVE `known`.
            #
            # The one carve-out: a value the operator wrote in profile.yaml's
            # `demographics:` block is his own answer, not a model guess, so serve it.
            # Scoped to `demographic_answer`'s five anchored EEO patterns and to
            # choice questions — real self-identification is always a select.
            #
            # Both halves of that scoping are scar tissue from 2026-09-11, when this
            # was implemented by simply moving the guard below `known`: that handed
            # the bypass to EVERY rule in _RULES, so a "Professional references (name,
            # email, LinkedIn)" label came back answered with the LinkedIn URL, and
            # the then-unanchored `\brace\b` answered "debug a race condition" with
            # the word "White" — gap_reason None, sheet reporting nothing left to do.
            configured = (
                demographic_answer(question.label, self.profile) if question.is_choice else None
            )
            if configured is None:
                return ComposedAnswer(
                    question, None, "demographic/reference question — answer this yourself"
                )
            return SourcedAnswer(configured)
        if question.label in self.known:
            # Presence, not truthiness: known can legitimately map a label to ""
            # (_salary_expectation with no salary_target configured, by design —
            # E2 forbids letting the figure fall through to the LLM). `known.get(...)
            # or ...` treated that deliberate "" the same as absence and asked the
            # LLM to invent a number anyway.
            value = self.known[question.label]
            if value == "":
                return ComposedAnswer(
                    question, None, "no configured value for this field — answer this yourself"
                )
            return SourcedAnswer(value)
        return await self._stored_or_generated(question)

    async def _stored_or_generated(self, question: FormQuestion) -> ComposedAnswer | SourcedAnswer:
        # Shape-checked, not just presence-checked: Application.form_data
        # predates this feature and 8 rows in the live DB still hold the
        # removed browser-automation tool's flat label->string shape, on
        # which `[...]["answer"]` raises TypeError before _sheet ever gets
        # to rewrite the column — permanently breaking those jobs. Same
        # defensive pattern as answer_bank.promote_application. An empty
        # "answer" counts as absent for the same reason `known`'s "" does
        # above: it is not an answer, and treating it as a hit would paste
        # a blank into a real form.
        cached = self.job_cache.get(question.label)
        if isinstance(cached, dict) and isinstance(cached.get("answer"), str) and cached["answer"]:
            return SourcedAnswer(cached["answer"])
        if (
            is_bank_eligible(question.kind)
            and (bank_answer := self.answer_bank.get(normalize_question(question.label)))
            is not None
        ):
            return SourcedAnswer(bank_answer)
        return await self._generated(question)

    async def _generated(self, question: FormQuestion) -> ComposedAnswer | SourcedAnswer:
        if question.is_choice and len(question.options) > LLM_OPTION_LIMIT:
            return ComposedAnswer(
                question,
                None,
                f"pick your answer from the {len(question.options)} options on the form",
            )
        if self.llm_exhausted:
            return ComposedAnswer(question, None, _SPEND_LIMIT_REASON)
        try:
            answer = await generate_answer(
                question, self.profile, self.job, llm_caller=self.llm_caller
            )
        except GenerationError as error:
            # After a spend-limit failure every further call is doomed the
            # same way — one gap per remaining generated answer, no more
            # calls. Deterministic pre-population above is unaffected.
            cause = error.__cause__
            if isinstance(cause, Exception) and is_spend_limit(cause):
                self.llm_exhausted = True
                return ComposedAnswer(question, None, _SPEND_LIMIT_REASON)
            return ComposedAnswer(question, None, "answer generation failed — answer this yourself")
        return SourcedAnswer(answer, is_llm_generated=True)
