"""Compiles a tailored CV and makes it fit one page.

Two paths end here: a freshly selected CV is rendered, compiled and shrunk
until pdflatex reports one page, and a cached .tex (a machine that gained
latex) is compiled once with nothing left to shrink. Anything that cannot be
made to fit is discarded so the next prepare regenerates it.
"""

from dataclasses import dataclass, replace
from pathlib import Path

from moonlighter.application.cvgen.latex.compile import compile_pdf, latex_available, page_count
from moonlighter.application.cvgen.latex.cv_template import strip_marker_lines
from moonlighter.application.cvgen.latex.render import CVSelection, render_cv
from moonlighter.application.cvgen.pool.loader import CVPool
from moonlighter.core.log import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class TailoredCV:
    path: Path
    compiled: bool


def _discard(tex: Path) -> None:
    tex.unlink(missing_ok=True)
    # The sibling .pdf goes too (see the round-6 comment in service.py's
    # `_cached_answer`): the cache short-circuits on cv.pdf BEFORE any compile,
    # so a survivor would be served forever at zero LLM calls with the source
    # .tex already gone.
    tex.with_suffix(".pdf").unlink(missing_ok=True)
    # The .log goes too: page_count (compile.py) reads it, and a stale one
    # left behind after the .tex it describes is gone is a landmine for any
    # future caller that reads the log without a fresh compile_pdf call first.
    tex.with_suffix(".log").unlink(missing_ok=True)


def _after_compile_failure(tex: Path) -> TailoredCV | None:
    """Decides what a failed compile means for the document.

    compile_pdf returned None. No pdflatex: keep the .tex, retry later at
    no LLM cost. pdflatex present: the DOCUMENT is broken and will fail
    identically forever — discard, regenerate next time.
    """
    if not latex_available():
        return TailoredCV(tex, compiled=False)
    logger.warning("the generated CV does not compile — discarding %s, using default CV", tex)
    _discard(tex)
    return None


def after_compile(tex: Path) -> TailoredCV | None:
    """Compiles a cached .tex and enforces the one-page rule on it.

    The cached-.tex path (a machine that gained latex): compile, and enforce
    the one-page rule with nothing left to shrink — an overflowing cached
    document is discarded so the next prepare regenerates under the budget.
    """
    pdf = compile_pdf(tex)
    if pdf is None:
        return _after_compile_failure(tex)
    pages = page_count(tex)
    if pages is not None and pages > 1:
        logger.warning("the cached CV does not fit one page — discarding %s, using default CV", tex)
        _discard(tex)
        return None
    return TailoredCV(pdf, compiled=True)


def _bullet_owners(pool: CVPool) -> dict[str, int]:
    # Only EXPERIENCE bullets are droppable: prose ids only carry a
    # translation, and an open-source id the model misfiled under "bullets"
    # (both pass _known_ids) owns no experience — `bullet_id in owner` skips it.
    # Keyed on the experience's INDEX, not company+title: two stints at the
    # same company with the same title (a gap between them) would otherwise
    # collapse into one counter and let the "keeps another selected bullet"
    # guard pass when it should not.
    return {
        bullet.id: index
        for index, experience in enumerate(pool.experiences)
        for bullet in experience.bullets
    }


def _droppable_bullet_index(selection: CVSelection, owner: dict[str, int]) -> int | None:
    selected_per_experience: dict[int, int] = {}
    for bullet_id in selection.bullets:
        if bullet_id in owner:
            selected_per_experience[owner[bullet_id]] = (
                selected_per_experience.get(owner[bullet_id], 0) + 1
            )
    for index in range(len(selection.bullets) - 1, -1, -1):
        bullet_id = selection.bullets[index]
        if bullet_id in owner and selected_per_experience[owner[bullet_id]] > 1:
            return index
    return None


def _shrunk(selection: CVSelection, pool: CVPool) -> CVSelection | None:
    """The same selection with one less thing on the page, or None when nothing can go.

    The last experience bullet whose experience keeps at least one other
    selected bullet goes first, then the last open-source id.
    """
    index = _droppable_bullet_index(selection, _bullet_owners(pool))
    if index is not None:
        return replace(
            selection, bullets=selection.bullets[:index] + selection.bullets[index + 1 :]
        )
    if selection.open_source:
        return replace(selection, open_source=selection.open_source[:-1])
    return None


def fit_to_one_page(
    out: Path, template: str, selection: CVSelection, *, pool: CVPool
) -> TailoredCV | None:
    """Render, compile, and drop content from the end until pdflatex reports one page.

    Deterministic and LLM-free: the model already ordered every list
    most-relevant-first, so the tail is what goes.
    """
    tex = out / "cv.tex"
    current: CVSelection | None = selection
    while current is not None:
        tex.write_text(strip_marker_lines(render_cv(template, current, pool)))
        pdf = compile_pdf(tex)
        if pdf is None:
            return _after_compile_failure(tex)
        pages = page_count(tex)
        if pages is None or pages == 1:
            return TailoredCV(pdf, compiled=True)
        current = _shrunk(current, pool)
    logger.warning(
        "the generated CV does not fit one page even at minimum — discarding %s, using default CV",
        tex,
    )
    _discard(tex)
    return None
