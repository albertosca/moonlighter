"""One question's outcome: either an answer to paste, or the reason it is a gap."""

from dataclasses import dataclass

from moonlighter.application.assisted.questions import FormQuestion


@dataclass(frozen=True)
class ComposedAnswer:
    question: FormQuestion
    answer: str | None
    gap_reason: str | None

    def __post_init__(self) -> None:
        if (self.answer is None) == (self.gap_reason is None):
            raise ValueError("a composed answer is either answered or a gap, never both or neither")
