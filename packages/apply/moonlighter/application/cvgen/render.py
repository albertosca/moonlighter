"""Renders the tailored CV .tex from the operator's template + a selection.

The template is a complete moderncv document owned by the operator (header,
contact block, Education, section headings — one file per language, pre-
translated) carrying four marker lines: %%SUMMARY%%, %%TECHNICAL_EXPERTISE%%,
%%EXPERIENCE%%, %%OPEN_SOURCE%%. Pool bullets are stored as LaTeX and pass
through untouched (modulo PT translations); generated prose (summary,
technical expertise) is mechanically escaped here — the model never emits
markup beyond **bold**."""

import re
from dataclasses import dataclass

from moonlighter.application.cvgen.pool import CVPool, PoolExperience
from moonlighter.core.log import get_logger

logger = get_logger(__name__)

# Single-pass lookup table prevents cascade re-escaping: braces produced by
# \textbackslash{} cannot be re-escaped on a subsequent pass.
_LATEX_ESCAPE_TABLE = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def escape_latex(text: str) -> str:
    # Single-pass regex prevents cascade: braces in \textbackslash{} won't
    # be re-escaped to \{ and \}.
    text = re.sub(r"[\\&%$#_{}~^]", lambda m: _LATEX_ESCAPE_TABLE[m.group()], text)
    return _BOLD.sub(r"\\textbf{\1}", text)


@dataclass(frozen=True)
class CVSelection:
    language: str
    summary: str
    technical_expertise: str
    bullets: tuple[str, ...]
    open_source: tuple[str, ...]
    translations: dict[str, str]


# --- the translation guard: a POSITIVE full-match grammar, never a blocklist --
#
# A PT translation replaces a pool bullet's LaTeX verbatim (_bullet_text below)
# and the result is compiled by a local pdflatex into a PDF the operator uploads
# to an employer. It is markup, not prose, so it cannot be escaped without
# destroying the pool's own \textbf{} style — it has to be validated. What the
# validation must NOT be is a blocklist, and two earlier attempts were:
#
#   1. They were subtractive — delete the allowed \textbf{...}/\textit{...}
#      spans with sub(), then scan what is left for forbidden characters. But
#      sub() REMOVES those spans, so nothing inside one was ever inspected:
#      \textbf{<anything>} was a free pass through the very check meant to gate
#      it. You cannot scan what you deleted.
#   2. TeX turns '^^hh' into the byte hh during TOKENIZATION, before any macro
#      exists, so '^^5c' IS a backslash and '^^7b'/'^^7d' ARE braces (and '^^'
#      plus a raw 0x1c is a backslash too). A check hunting for a literal
#      backslash finds none in '^^5cinput^^7b/etc/secret^^7d' — which pdflatex
#      reads as \input{/etc/secret} and embeds that file in the uploaded PDF.
#      Measured, not theorised: rc=0, canary text inside the compiled PDF.
#
# Hence: the whole string must MATCH end to end, and the only backslash the
# grammar can produce is the '\textbf'/'\textit' it spells out itself. Every TeX
# special is excluded from the argument class as well as from the text around
# it — '^' above all, as the caret route to a control sequence.
#
# Do NOT "simplify" this back into sub()-then-search, and do not widen the
# character class to let a stray '%', '&' or '$' through: a translation that
# fails the grammar simply keeps its curated pool latex, which is the design's
# own safe default for a dropped translation.
_SAFE_TEXT = r"[^{}\\^~$&#%_]*"
_TRANSLATION_OK = re.compile(rf"\A{_SAFE_TEXT}(?:\\text(?:bf|it)\{{{_SAFE_TEXT}\}}{_SAFE_TEXT})*\Z")


def is_safe_translation(text: str) -> bool:
    """True when a model-authored translation may reach the .tex verbatim."""
    return _TRANSLATION_OK.fullmatch(text) is not None


def _bullet_text(bullet_id: str, latex: str, selection: CVSelection) -> str:
    # The render-time chokepoint: every model-controlled unescaped string
    # passes here just before substitution. decide_cv applies the same
    # predicate, and is today the only producer of a CVSelection — validating
    # again here is what makes the curated fallback the DEFAULT rather than
    # something each future producer has to remember.
    text = selection.translations.get(bullet_id)
    if text is None:
        return latex
    if not is_safe_translation(text):
        logger.warning("unsafe translation for %s — rendering the pool bullet", bullet_id)
        return latex
    return text


def _entry(exp: PoolExperience, selection: CVSelection) -> str:
    if exp.prose is not None:
        prose = _bullet_text(exp.prose_id or "", exp.prose, selection)
        return (
            f"\\cventry{{}}{{{exp.title}}}{{{exp.company}}}{{{exp.period}}}"
            f"{{{exp.location}}}{{{prose}}}"
        )
    chosen = [b for bid in selection.bullets for b in exp.bullets if b.id == bid]
    if not chosen:
        # Spec: empty validated selection falls back to every base bullet —
        # dropping an employment period is worse than generic emphasis.
        chosen = list(exp.bullets)
    items = "\n".join(f"    \\item {_bullet_text(b.id, b.latex, selection)}" for b in chosen)
    return (
        f"\\cventry{{}}{{{exp.title}}}{{{exp.company}}}{{{exp.period}}}{{{exp.location}}}{{\n"
        f"\\begin{{itemize}}\n{items}\n\\end{{itemize}}\n}}"
    )


def _open_source_block(selection: CVSelection, pool: CVPool) -> str:
    chosen = [b for bid in selection.open_source for b in pool.open_source if b.id == bid]
    if not chosen:
        return ""
    # Domain jargon, deliberately untranslated in both PT and EN:
    # "Open Source" is used as-is in Brazilian tech CVs, same convention as
    # the pool's job titles (e.g., "Full Stack Engineer" stays untranslated).
    heading = "Open Source"
    items = "\n".join(f"\\cvlistitem{{{_bullet_text(b.id, b.latex, selection)}}}" for b in chosen)
    return f"\\section{{{heading}}}\n{items}"


def render_cv(template: str, selection: CVSelection, pool: CVPool) -> str:
    experience = "\n\n".join(_entry(exp, selection) for exp in pool.experiences)
    return (
        template.replace("%%SUMMARY%%", escape_latex(selection.summary))
        .replace("%%TECHNICAL_EXPERTISE%%", escape_latex(selection.technical_expertise))
        .replace("%%EXPERIENCE%%", experience)
        .replace("%%OPEN_SOURCE%%", _open_source_block(selection, pool))
    )
