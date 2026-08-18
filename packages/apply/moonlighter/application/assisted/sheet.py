"""Render the whole application as one reviewable block.

The whole application, not a screenshot of part of it: the automation this
replaces reviewed a 4 500 px form through a viewport capture showing 17% of it.
"""

from moonlighter.application.assisted.composer import ComposedAnswer
from moonlighter.application.assisted.questions import QuestionKind

GAP = "!! I DON'T KNOW"
NO_QUESTIONS_FOUND = (
    "!! NO QUESTIONS FOUND — question discovery returned nothing. "
    "This is not a completed application: open the form yourself and check it by hand."
)


def _entry(index: int, total: int, item: ComposedAnswer) -> str:
    question = item.question
    marks = ["required"] if question.required else []
    if question.kind is QuestionKind.MULTI_SELECT:
        marks.append(f"pick any of {len(question.options)}")
    elif question.is_choice:
        marks.append(f"pick 1 of {len(question.options)}")
    suffix = f"  ({', '.join(marks)})" if marks else ""

    lines = [f"[{index}/{total}] {question.label}{suffix}"]
    if item.answer is None:
        lines.append(f"{GAP} — {item.gap_reason}")
    elif question.is_choice:
        lines.append(f"> {item.answer}")
        others = [o for o in question.options if o != item.answer]
        if others:
            lines.append(f"  not chosen: {' / '.join(others)}")
    else:
        lines.append(item.answer)
    return "\n".join(lines)


def render_sheet(
    composed: list[ComposedAnswer], *, job_title: str, company: str, apply_url: str
) -> str:
    total = len(composed)
    header = [f"{job_title} — {company}", apply_url, ""]

    if total == 0:
        return "\n".join([*header, NO_QUESTIONS_FOUND])

    gaps = sum(1 for item in composed if item.answer is None)
    body = [_entry(i, total, item) for i, item in enumerate(composed, start=1)]
    footer = (
        f"{gaps} of {total} need you"
        if gaps
        else f"All {total} answered — nothing left for you but to paste and submit."
    )
    return "\n".join([*header, "\n\n".join(body), "", footer])
