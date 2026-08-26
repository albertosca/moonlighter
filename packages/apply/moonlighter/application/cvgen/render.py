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

# Order matters: backslash first, then the rest, then ** -> \textbf.
_SPECIALS = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def escape_latex(text: str) -> str:
    for char, repl in _SPECIALS:
        text = text.replace(char, repl)
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
    return selection.translations.get(bullet_id, latex)


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
