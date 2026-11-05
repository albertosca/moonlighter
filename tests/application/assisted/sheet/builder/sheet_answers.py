"""Builders for the composed answers a sheet is rendered from, and the paragraph picker the sheet tests read with."""

from moonlighter.application.assisted.composition.composed_answer import ComposedAnswer
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

HEADER = {"job_title": "Staff Engineer", "company": "acme", "apply_url": "https://x/apply"}


def answered(label: str, answer: str, *, required: bool = True) -> ComposedAnswer:
    return ComposedAnswer(
        FormQuestion(label=label, kind=QuestionKind.TEXT, required=required), answer, None
    )


def gap(label: str, reason: str) -> ComposedAnswer:
    return ComposedAnswer(
        FormQuestion(label=label, kind=QuestionKind.TEXT, required=True), None, reason
    )


def choice(
    label: str, options: tuple[str, ...], picked: str, *, required: bool = True
) -> ComposedAnswer:
    return ComposedAnswer(
        FormQuestion(
            label=label, kind=QuestionKind.SINGLE_SELECT, required=required, options=options
        ),
        picked,
        None,
    )


def multi_choice(
    label: str, options: tuple[str, ...], picked: str, *, required: bool = True
) -> ComposedAnswer:
    return ComposedAnswer(
        FormQuestion(
            label=label, kind=QuestionKind.MULTI_SELECT, required=required, options=options
        ),
        picked,
        None,
    )


def entry_block(sheet: str, marker: str) -> str:
    """Return the single entry paragraph that starts with `marker`, isolated from the rest."""
    entries = sheet.split("\n\n")
    matches = [entry for entry in entries if entry.startswith(marker)]
    assert len(matches) == 1, f"expected exactly one entry starting with {marker!r}, got {matches}"
    return matches[0]
