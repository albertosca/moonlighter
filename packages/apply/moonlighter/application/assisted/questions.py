"""The one shape every question source produces."""

from dataclasses import dataclass
from enum import StrEnum


class QuestionKind(StrEnum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    FILE = "file"
    BOOLEAN = "boolean"


_CHOICE_KINDS = frozenset({QuestionKind.SINGLE_SELECT, QuestionKind.MULTI_SELECT})


@dataclass(frozen=True)
class FormQuestion:
    label: str
    kind: QuestionKind
    required: bool
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind in _CHOICE_KINDS and not self.options:
            raise ValueError(f"{self.kind} question {self.label!r} carries no options")

    @property
    def is_choice(self) -> bool:
        return self.kind in _CHOICE_KINDS
