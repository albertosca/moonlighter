"""Renders the tailored CV .tex from the operator's template + a selection.

The template is a complete moderncv document owned by the operator (header,
contact block, Education, section headings — one file per language, pre-
translated) carrying four marker lines: %%SUMMARY%%, %%TECHNICAL_EXPERTISE%%,
%%EXPERIENCE%%, %%OPEN_SOURCE%%. The operator's curated pool bullets are
stored as LaTeX and pass through untouched. EVERY model-authored string —
summary, technical expertise, and PT translations alike — is mechanically
escaped here instead: the model is asked for plaintext and emits no markup
beyond **bold**, so escaping is lossless and nothing it writes can become a
command in the .tex.
"""

from dataclasses import dataclass
from typing import Final

from moonlighter.application.cvgen.latex.text import escape_latex
from moonlighter.application.cvgen.pool.loader import CVPool, PoolExperience

# One-page rule (Alberto, 2026-09-02). Measured on the real template: the
# grouped layout fits 9 bullets plus the three prose entries on one page; the
# orchestrator still verifies the page count and shrinks if the model's
# choices run long.
MAXIMUM_BULLETS: Final = 9
MAXIMUM_OPEN_SOURCE: Final = 1


@dataclass(frozen=True)
class CVSelection:
    language: str
    summary: str
    technical_expertise: str
    bullets: tuple[str, ...]
    open_source: tuple[str, ...]
    translations: dict[str, str]


def _bullet_text(bullet_id: str, latex: str, selection: CVSelection) -> str:
    r"""The pool's curated latex, or a model translation escaped into plaintext.

    The two arguments are NOT the same kind of text, which is the whole point:
    `latex` is operator-curated markup and must pass through untouched (escaping
    it would print \textbf{...} as visible characters in the CV), while a
    translation is model prose in the same **bold** dialect the summary uses and
    is escaped here.

    This is where every model-controlled string meets the .tex, and escaping is
    what makes the content of that string irrelevant. Two earlier designs tried
    to let translations carry LaTeX and VALIDATE them instead; both were
    bypassed, most instructively via '^^hh' — TeX turns it into the byte hh at
    TOKENIZATION, so '^^5c' is a backslash that no check for a literal backslash
    can see, and \input{/etc/secret} then embedded a local file into the PDF the
    operator uploads to an employer. escape_latex has no such blind spot: it
    rewrites every TeX special, '^' included, so there is nothing left to hunt
    for. Do not reintroduce a "trusted markup" path for model output here.
    """
    text = selection.translations.get(bullet_id)
    if text is None:
        return latex
    # Whitespace-only or zero-width-only input escapes to "", and rendering
    # that silently deletes the bullet from the CV. Empty is not a
    # translation: fall back to the curated latex, same as an absent one.
    return escape_latex(text) or latex


def _period_bounds(period: str) -> tuple[str, str]:
    parts = [part.strip() for part in period.split("--", 1)]
    return (parts[0], parts[-1])


def _entry(
    experience: PoolExperience,
    selection: CVSelection,
    role_period: str,
    *,
    header: tuple[str, str, str],
) -> str:
    r"""One \cventry.

    `header` = (company, span, location) — empty strings for a follow-up role
    in a grouped block, which makes moderncv banking skip the bold company line
    (its own multi-role convention).
    """
    company, span, location = header
    head = f"\\cventry{{{role_period}}}{{{experience.title}}}{{{company}}}{{{span}}}{{{location}}}"
    if experience.prose is not None:
        return f"{head}{{{_bullet_text(experience.prose_id or '', experience.prose, selection)}}}"
    chosen = [
        bullet
        for bullet_id in selection.bullets
        for bullet in experience.bullets
        if bullet.id == bullet_id
    ]
    if not chosen:
        # One-page rule: an unselected experience keeps its period through its
        # FIRST curated bullet, not all of them — every bullet would fight the
        # page budget and make the shrink loop grow the document.
        chosen = list(experience.bullets[:1])
    items = "\n".join(
        f"    \\item {_bullet_text(bullet.id, bullet.latex, selection)}" for bullet in chosen
    )
    return f"{head}{{\n\\begin{{itemize}}\n{items}\n\\end{{itemize}}\n}}"


def _last_of_company_run(experiences: tuple[PoolExperience, ...], first: int) -> int:
    last = first
    while (
        last + 1 < len(experiences) and experiences[last + 1].company == experiences[first].company
    ):
        last += 1
    return last


def _run_entries(
    experiences: tuple[PoolExperience, ...], first: int, last: int, *, selection: CVSelection
) -> list[str]:
    head = experiences[first]
    if last == first:
        return [_entry(head, selection, "", header=(head.company, head.period, head.location))]
    span = f"{_period_bounds(experiences[last].period)[0]} -- {_period_bounds(head.period)[1]}"
    entries = [_entry(head, selection, head.period, header=(head.company, span, head.location))]
    entries.extend(
        _entry(follow_up, selection, follow_up.period, header=("", "", ""))
        for follow_up in experiences[first + 1 : last + 1]
    )
    return entries


def _entries(pool: CVPool, selection: CVSelection) -> list[str]:
    entries: list[str] = []
    first = 0
    while first < len(pool.experiences):
        last = _last_of_company_run(pool.experiences, first)
        entries.extend(_run_entries(pool.experiences, first, last, selection=selection))
        first = last + 1
    return entries


def _open_source_block(selection: CVSelection, pool: CVPool) -> str:
    chosen = [
        bullet
        for bullet_id in selection.open_source
        for bullet in pool.open_source
        if bullet.id == bullet_id
    ]
    if not chosen:
        return ""
    # Domain jargon, deliberately untranslated in both PT and EN:
    # "Open Source" is used as-is in Brazilian tech CVs, same convention as
    # the pool's job titles (e.g., "Full Stack Engineer" stays untranslated).
    heading = "Open Source"
    items = "\n".join(
        f"\\cvlistitem{{{_bullet_text(bullet.id, bullet.latex, selection)}}}" for bullet in chosen
    )
    return f"\\section{{{heading}}}\n{items}"


def render_cv(template: str, selection: CVSelection, pool: CVPool) -> str:
    experience = "\n\n".join(_entries(pool, selection))
    return (
        template.replace("%%SUMMARY%%", escape_latex(selection.summary))
        .replace("%%TECHNICAL_EXPERTISE%%", escape_latex(selection.technical_expertise))
        .replace("%%EXPERIENCE%%", experience)
        .replace("%%OPEN_SOURCE%%", _open_source_block(selection, pool))
    )
