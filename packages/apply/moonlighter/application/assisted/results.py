"""The structured result of preparing an application sheet, and its renderer."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from moonlighter.application.assisted.composer import ComposedAnswer
from moonlighter.application.assisted.sheet import render_sheet


class SheetKind(StrEnum):
    SHEET = "sheet"  # a sheet was produced
    JOB_NOT_FOUND = "job_not_found"
    NEEDS_PASTE = "needs_paste"  # the API had no questions: paste the page
    NO_QUESTIONS = "no_questions"  # the pasted text had none


@dataclass(frozen=True)
class SheetResult:
    kind: SheetKind
    composed: list[ComposedAnswer]
    job_title: str
    company: str
    apply_url: str
    alias: str | None = None
    alias_note: str | None = None
    cv_note: str | None = None
    cv_path: str | None = None
    cv_compiled: bool | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if (self.error is not None) == (self.kind is SheetKind.SHEET):
            raise ValueError(
                f"SheetResult.error is set exactly when kind is not sheet (kind={self.kind})"
            )


def render_sheet_result(result: SheetResult) -> str:
    if result.error is not None:
        return result.error
    sheet = render_sheet(
        result.composed,
        job_title=result.job_title,
        company=result.company,
        apply_url=result.apply_url,
    )
    for note in (result.alias_note, result.cv_note):
        if note is not None:
            sheet += f"\n\n{note}"
    return sheet


def sheet_result_to_dict(result: SheetResult) -> dict[str, Any]:
    return {
        "kind": result.kind.value,
        "job_title": result.job_title,
        "company": result.company,
        "apply_url": result.apply_url,
        "alias": result.alias,
        "cv": (
            {"path": result.cv_path, "compiled": result.cv_compiled}
            if result.cv_path is not None
            else None
        ),
        "answers": [
            {
                "label": item.question.label,
                "kind": item.question.kind.value,
                "required": item.question.required,
                "options": list(item.question.options),
                "answer": item.answer,
                "gap_reason": item.gap_reason,
            }
            for item in result.composed
        ],
        "notes": {"alias": result.alias_note, "cv": result.cv_note},
        "error": result.error,
    }
