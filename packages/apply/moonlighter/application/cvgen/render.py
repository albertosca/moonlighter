"""Renders the tailored CV .tex from the operator's template + a selection.

The template is a complete moderncv document owned by the operator (header,
contact block, Education, section headings — one file per language, pre-
translated) carrying four marker lines: %%SUMMARY%%, %%TECHNICAL_EXPERTISE%%,
%%EXPERIENCE%%, %%OPEN_SOURCE%%. The operator's curated pool bullets are
stored as LaTeX and pass through untouched. EVERY model-authored string —
summary, technical expertise, and PT translations alike — is mechanically
escaped here instead: the model is asked for plaintext and emits no markup
beyond **bold**, so escaping is lossless and nothing it writes can become a
command in the .tex."""

import re
import unicodedata
from dataclasses import dataclass

from moonlighter.application.cvgen.pool import CVPool, PoolExperience

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

# Three classes of character are not TeX specials, so escaping leaves them
# untouched, and each is a FATAL pdflatex error that yields no PDF at all
# (measured, not assumed):
#   - a blank line inside \cventry's argument — "! Paragraph ended before
#     \cventry was complete". An ordinary "\n\n" from the model triggers it.
#   - U+2028/U+2029 and exotic spaces (U+2002...) — "Unicode character not set
#     up for use with LaTeX".
#   - control (Cc) and format (Cf: U+200B, U+200E, soft hyphen) characters.
# All three carry no text, so collapsing and dropping them mangles nothing.
# Whitespace collapsing runs first and absorbs everything Python calls
# whitespace (newlines, tabs, Zl, Zp, Zs); the category pass then removes what
# is left, which is the non-whitespace Cc and every Cf.
#
# What is deliberately NOT dropped: letters LaTeX cannot typeset (CJK, Greek,
# emoji). Those carry meaning, and silently deleting one REWRITES a factual
# claim in a document the candidate signs. The compile fails instead, and
# service._after_compile turns that into an honest degrade-and-regenerate.
_WHITESPACE = re.compile(r"\s+")
_DROPPED_CATEGORIES = frozenset({"Cc", "Cf"})


def escape_latex(text: str) -> str:
    # Single-pass regex prevents cascade: braces in \textbackslash{} won't
    # be re-escaped to \{ and \}.
    text = _WHITESPACE.sub(" ", text).strip()
    text = "".join(c for c in text if unicodedata.category(c) not in _DROPPED_CATEGORIES)
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


def _bullet_text(bullet_id: str, latex: str, selection: CVSelection) -> str:
    """The pool's curated latex, or a model translation escaped into plaintext.

    The two arguments are NOT the same kind of text, which is the whole point:
    `latex` is operator-curated markup and must pass through untouched (escaping
    it would print \\textbf{...} as visible characters in the CV), while a
    translation is model prose in the same **bold** dialect the summary uses and
    is escaped here.

    This is where every model-controlled string meets the .tex, and escaping is
    what makes the content of that string irrelevant. Two earlier designs tried
    to let translations carry LaTeX and VALIDATE them instead; both were
    bypassed, most instructively via '^^hh' — TeX turns it into the byte hh at
    TOKENIZATION, so '^^5c' is a backslash that no check for a literal backslash
    can see, and \\input{/etc/secret} then embedded a local file into the PDF the
    operator uploads to an employer. escape_latex has no such blind spot: it
    rewrites every TeX special, '^' included, so there is nothing left to hunt
    for. Do not reintroduce a "trusted markup" path for model output here.
    """
    text = selection.translations.get(bullet_id)
    return latex if text is None else escape_latex(text)


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
