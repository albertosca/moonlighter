"""Lever card templates: the JSON behind a form's custom questions."""

import json
from typing import Any

from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

_CARD_KINDS = {
    "text": QuestionKind.TEXT,
    "textarea": QuestionKind.LONG_TEXT,
    "dropdown": QuestionKind.SINGLE_SELECT,
    "multiple-choice": QuestionKind.SINGLE_SELECT,
    "multiple-select": QuestionKind.MULTI_SELECT,
}
_CHOICE_KINDS = (QuestionKind.SINGLE_SELECT, QuestionKind.MULTI_SELECT)


def _card_question(field: dict[str, Any]) -> FormQuestion:
    kind = _CARD_KINDS.get(str(field.get("type")), QuestionKind.LONG_TEXT)
    options = _options(field) if kind in _CHOICE_KINDS else ()
    if kind in _CHOICE_KINDS and not options:
        kind = QuestionKind.LONG_TEXT
    return FormQuestion(
        label=str(field["text"]),
        kind=kind,
        required=bool(field.get("required")),
        options=options,
    )


def card_questions(template: str) -> list[FormQuestion]:
    card = json.loads(template)
    if not isinstance(card, dict):
        raise ValueError("a Lever card template is not a JSON object")  # noqa: TRY004 - a malformed template is a ValueError, like json's own decode error
    fields = card.get("fields")
    if not isinstance(fields, list):
        raise ValueError("a Lever card template has no list of fields")  # noqa: TRY004 - a malformed template is a ValueError, like json's own decode error
    return [
        _card_question(field) for field in fields if isinstance(field, dict) and field.get("text")
    ]


def _options(field: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(option["text"])
        for option in field.get("options") or []
        if isinstance(option, dict) and option.get("text")
    )
