"""Render the whole application as one reviewable block.

The whole application, not a screenshot of part of it: the automation this
replaces reviewed a 4 500 px form through a viewport capture showing 17% of it.
"""

from moonlighter.application.assisted.composition.composed_answer import ComposedAnswer
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

GAP = "!! I DON'T KNOW"
NO_QUESTIONS_FOUND = (
    "!! NO QUESTIONS FOUND — question discovery returned nothing. "
    "This is not a completed application: open the form yourself and check it by hand."
)

# Beyond this many unchosen options the "not chosen" line is a count, not a list:
# a Lever select of 3,301 countries made one question ~105 KB of sheet.
LISTED_UNCHOSEN_LIMIT = 20


def _not_chosen(others: list[str]) -> list[str]:
    if not others:
        return []
    if len(others) > LISTED_UNCHOSEN_LIMIT:
        return [f"  not chosen: {len(others)} other options (see the form)"]
    return [f"  not chosen: {' / '.join(others)}"]


def _marks(question: FormQuestion) -> list[str]:
    marks = ["required"] if question.required else []
    if question.kind is QuestionKind.MULTI_SELECT:
        marks.append(f"pick any of {len(question.options)}")
    elif question.is_choice:
        marks.append(f"pick 1 of {len(question.options)}")
    return marks


def _answer_lines(item: ComposedAnswer) -> list[str]:
    question = item.question
    if item.answer is None:
        return [f"{GAP} — {item.gap_reason}"]
    if question.kind is QuestionKind.MULTI_SELECT:
        chosen = item.answer.split("\n")
        others = [option for option in question.options if option not in chosen]
        return [*(f"> {pick}" for pick in chosen), *_not_chosen(others)]
    if question.is_choice:
        others = [option for option in question.options if option != item.answer]
        return [f"> {item.answer}", *_not_chosen(others)]
    return [item.answer]


def _entry(index: int, total: int, item: ComposedAnswer) -> str:
    question = item.question
    marks = _marks(question)
    suffix = f"  ({', '.join(marks)})" if marks else ""
    return "\n".join([f"[{index}/{total}] {question.label}{suffix}", *_answer_lines(item)])


def render_sheet(
    composed: list[ComposedAnswer], *, job_title: str, company: str, apply_url: str
) -> str:
    total = len(composed)
    header = [f"{job_title} — {company}", apply_url, ""]

    if total == 0:
        return "\n".join([*header, NO_QUESTIONS_FOUND])

    gaps = sum(1 for item in composed if item.answer is None)
    body = [_entry(index, total, item) for index, item in enumerate(composed, start=1)]
    footer = (
        f"{gaps} of {total} need you"
        if gaps
        else f"All {total} answered — nothing left for you but to paste and submit."
    )
    return "\n".join([*header, "\n\n".join(body), "", footer])
