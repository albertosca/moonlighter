"""The structured result of preparing an application sheet, and its renderer."""

from dataclasses import dataclass

from moonlighter.application.assisted.composer import ComposedAnswer
from moonlighter.application.assisted.sheet import render_sheet


@dataclass(frozen=True)
class SheetResult:
    composed: list[ComposedAnswer]
    job_title: str
    company: str
    apply_url: str
    alias: str | None = None
    alias_note: str | None = None
    cv_note: str | None = None
    error: str | None = None


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
