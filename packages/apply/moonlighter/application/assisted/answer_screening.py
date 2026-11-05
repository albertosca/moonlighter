"""Screen a sourced answer before it reaches the sheet, and pin a choice to an offered option."""

import re

from moonlighter.application.answers.matching.option_matcher import match_option_locally
from moonlighter.application.answers.needs_review import NEEDS_REVIEW_SENTINEL
from moonlighter.application.answers.operator_guard import find_operator_marker
from moonlighter.application.assisted.composed_answer import ComposedAnswer
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind


def screen_answer(question: FormQuestion, answer: str | None) -> ComposedAnswer:
    """The answer as it will be pasted, or the gap it becomes when it is not safe to paste."""
    # pre_populate_answers can hand back its own review sentinel instead of a real
    # value (work-authorization/sponsorship fields when the country can't be inferred;
    # salary fields when the units disagree) — for ANY question kind, not just choices.
    # Screened unconditionally, before is_choice, so it never reaches a TEXT/LONG_TEXT
    # field as a literal "__NEEDS_REVIEW__" answer pasted into a real form.
    if answer == NEEDS_REVIEW_SENTINEL:
        return ComposedAnswer(question, None, "no defensible answer here — answer this yourself")

    if answer is None:
        return ComposedAnswer(question, None, "no basis in your profile to answer")

    if not question.is_choice and (marker := find_operator_marker(answer)) is not None:
        return ComposedAnswer(
            question,
            None,
            f'the model addressed the operator ("{marker}...") — answer this yourself',
        )

    return _match_choice(question, answer)


def _match_choice(question: FormQuestion, answer: str) -> ComposedAnswer:
    if question.kind is QuestionKind.MULTI_SELECT:
        picks = _picked_options(question, answer)
        if not picks:
            return ComposedAnswer(question, None, "no offered option matches — pick yourself")
        return ComposedAnswer(question, "\n".join(picks), None)
    if question.is_choice:
        picked = match_option_locally(answer, list(question.options))
        if picked is None:
            return ComposedAnswer(question, None, "no offered option matches — pick one yourself")
        return ComposedAnswer(question, picked, None)
    return ComposedAnswer(question, answer, None)


def _picked_options(question: FormQuestion, answer: str) -> list[str]:
    picks: list[str] = []
    for part in re.split(r"[\n,]+", answer):
        matched = match_option_locally(part.strip(), list(question.options))
        if matched and matched not in picks:
            picks.append(matched)
    return picks
