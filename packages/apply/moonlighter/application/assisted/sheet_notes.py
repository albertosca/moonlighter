"""What a sheet says besides the answers: the tracking alias, the CV to upload, the form cache."""

import json
from pathlib import Path
from typing import Any

from moonlighter.application.assisted.composed_answer import ComposedAnswer
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.cvgen.service import TailoredCV
from moonlighter.core.email_alias import is_email_label


def takes_alias(question: FormQuestion) -> bool:
    return (
        is_email_label(question.label)
        and not question.is_choice
        and question.kind is not QuestionKind.FILE
    )


def with_tracking_alias(composed: list[ComposedAnswer], alias: str) -> list[ComposedAnswer]:
    """Answer every email field with the alias, including one the composer left as a gap.

    Tracking must not depend on the profile carrying an email address.
    """
    return [
        ComposedAnswer(item.question, alias, None) if takes_alias(item.question) else item
        for item in composed
    ]


def alias_note(composed: list[ComposedAnswer], alias: str | None) -> str | None:
    if alias is None or any(takes_alias(item.question) for item in composed):
        return None
    # No email question reached the sheet (a paste that missed it, a source
    # that omits standard fields) — the alias must reach the operator anyway,
    # or the company's reply lands in a mailbox the monitor never reads.
    return f"Where the form asks for an email address, use: {alias}"


def _well_shaped(entry: Any) -> bool:
    """Whether a per-job cache entry has this feature's {"answer": str, "kind": str} shape.

    Rows written by the removed browser-automation tool are a flat
    label->string mapping instead (8 of them in the live DB). compose_answers
    ignores those on read but cannot remove them; dropping them here lets the
    row self-heal into the new shape the first time a sheet is prepared,
    instead of carrying the legacy junk forward forever.
    """
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("answer"), str)
        and isinstance(entry.get("kind"), str)
    )


def well_shaped_form_data(job_cache: dict[str, Any]) -> str:
    return json.dumps({label: value for label, value in job_cache.items() if _well_shaped(value)})


def _names_path(composed: list[ComposedAnswer], path: Path) -> bool:
    """Whether some gap already tells the operator to upload this exact file."""
    return any(item.gap_reason is not None and str(path) in item.gap_reason for item in composed)


def cv_note(tailored: TailoredCV | None, composed: list[ComposedAnswer]) -> str | None:
    if tailored is None:
        return None
    if not tailored.compiled:
        # The CV gap names the DEFAULT CV here (resolve_cv_path refuses a dir
        # with no pdf), so "compile it" alone leaves the operator compiling a
        # tailored CV and then uploading the generic one.
        return (
            f"A tailored CV was generated but pdflatex is not installed —"
            f" compile it yourself: cd {tailored.path.parent} && pdflatex {tailored.path.name}"
            f" — then upload the resulting cv.pdf instead of the CV named above"
            f" (review it first)"
        )
    if _names_path(composed, tailored.path):
        return None
    # Same shape as the alias footer: the compiled CV otherwise
    # surfaces only through the composer's CV FILE branch, which needs a
    # FILE question with a CV-shaped label. A paste that missed the resume
    # field would leave a tailored PDF nobody is told to review or upload.
    return (
        f"Upload this CV for this job: {tailored.path}"
        f" (tailored for this job — review it before uploading)"
    )
