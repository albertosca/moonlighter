"""The operator's CV templates: which one to read, and the base text it declares.

A template carries `%%BASE_SUMMARY:` / `%%BASE_EXPERTISE:` declaration lines
that are metadata for the generator, never content. This module reads the
template for a language, parses those declarations, strips them from a
rendered document, and re-points a selection at the right language's base.
"""

import re
from dataclasses import replace
from typing import Any, NamedTuple

from moonlighter.application.cvgen.latex.render import CVSelection
from moonlighter.application.cvgen.paths import resolved_template_dir
from moonlighter.core.log import get_logger

logger = get_logger(__name__)

# The captured text is treated as plain model prose (escape_latex + the
# **bold** dialect, same as everything else generate.py produces) — an
# operator writing raw LaTeX on one of these two lines (e.g. \textbf{...})
# gets it printed literally, with the backslash and braces escaped.
_BASE_SUMMARY = re.compile(r"^%%BASE_SUMMARY: (.+)$", re.MULTILINE)
_BASE_EXPERTISE = re.compile(r"^%%BASE_EXPERTISE: (.+)$", re.MULTILINE)
_MARKER_LINES = re.compile(r"^%%BASE_(SUMMARY|EXPERTISE): .+\n", re.MULTILINE)


class BaseFields(NamedTuple):
    """The base text a template declares for its summary and expertise lines."""

    summary: str
    expertise: str


def base_fields(template: str) -> BaseFields:
    """The (summary, expertise) base text a template declares for itself.

    Public because the bootstrap (cvgen/pool/bootstrap.py) renders a SAMPLE of the
    pool it just drafted through the template it just filled, and that sample
    needs the same two fields service.py feeds the per-job generator. One
    definition, not two regexes drifting apart across modules — an empty
    string for either is a template that simply declares no base, exactly as
    the per-job path already treats it.
    """
    summary = match.group(1) if (match := _BASE_SUMMARY.search(template)) else ""
    expertise = match.group(1) if (match := _BASE_EXPERTISE.search(template)) else ""
    return BaseFields(summary, expertise)


def strip_marker_lines(rendered: str) -> str:
    """Drops the BASE_SUMMARY/BASE_EXPERTISE declaration lines from a rendered document.

    They are metadata for the generator, never content: pdflatex reads them as
    ordinary comments, but leaving them in a finished .tex means the next
    reader cannot tell a declaration from the summary it describes. Shared with
    the bootstrap's sample render for the same reason.
    """
    return _MARKER_LINES.sub("", rendered)


def template_text(config: dict[str, Any], language: str) -> str | None:
    template_directory = resolved_template_dir(config)
    english_path = template_directory / "cv-template.en.tex"
    portuguese_path = template_directory / "cv-template.pt.tex"
    if language == "pt":
        if portuguese_path.exists():
            return portuguese_path.read_text()
        logger.warning("no PT template — rendering the tailored CV in English")
    return english_path.read_text() if english_path.exists() else None


def relanguage_fallback_fields(
    selection: CVSelection, template: str, english_base: BaseFields
) -> CVSelection | None:
    """Re-points a field that fell back to the English base at the chosen template's base.

    decide_cv parses %%BASE_SUMMARY%%/%%BASE_EXPERTISE%% out of en_template
    before it can know the posting's language (the model reveals it only in
    its own response), so a field it rejects as non-typesettable falls back to
    the ENGLISH base there — harmless while that base only fed the prompt, but
    the fallback to base text made it land in the rendered CV. A field equal to
    the English base is exactly the fallback's signature: re-point it at the
    base text of the template actually selected for rendering, or degrade the
    whole CV to None when that language has no base of its own to offer.
    """
    used_en_summary = selection.summary == english_base.summary
    used_en_expertise = selection.technical_expertise == english_base.expertise
    if not used_en_summary and not used_en_expertise:
        return selection
    lang_base_summary, lang_base_expertise = base_fields(template)
    if (used_en_summary and not lang_base_summary) or (
        used_en_expertise and not lang_base_expertise
    ):
        logger.warning(
            "cv summary/expertise fell back to English base with no %s base to replace it — "
            "using default CV",
            selection.language,
        )
        return None
    return replace(
        selection,
        summary=lang_base_summary if used_en_summary else selection.summary,
        technical_expertise=lang_base_expertise
        if used_en_expertise
        else selection.technical_expertise,
    )
