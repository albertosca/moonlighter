"""Orchestrates tailored-CV generation for one job — cache, degrade, compile.

Opt-in by existence: no cv.pool in config (or the file missing) means the
feature is off and this function is a cheap None. Every failure path degrades
to None so the application always proceeds with the default CV."""

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from moonlighter.application.cvgen.compile import compile_pdf, latex_available, page_count
from moonlighter.application.cvgen.generate import USE_BASE, decide_cv
from moonlighter.application.cvgen.pool import CVPool, PoolError, load_pool
from moonlighter.application.cvgen.render import CVSelection, render_cv
from moonlighter.core.config import resolve_under_home
from moonlighter.core.llm import LLMCaller, is_spend_limit
from moonlighter.core.log import get_logger

logger = get_logger(__name__)

_BASE_SUMMARY = re.compile(r"^%%BASE_SUMMARY: (.+)$", re.MULTILINE)
_BASE_EXPERTISE = re.compile(r"^%%BASE_EXPERTISE: (.+)$", re.MULTILINE)
_MARKER_LINES = re.compile(r"^%%BASE_(SUMMARY|EXPERTISE): .+\n", re.MULTILINE)


@dataclass(frozen=True)
class TailoredCV:
    path: Path
    compiled: bool


def _discard(tex: Path) -> None:
    tex.unlink(missing_ok=True)
    # The sibling .pdf goes too (see the round-6 comment): the cache
    # short-circuits on cv.pdf BEFORE any compile, so a survivor would be
    # served forever at zero LLM calls with the source .tex already gone.
    tex.with_suffix(".pdf").unlink(missing_ok=True)


def _after_compile_failure(tex: Path) -> TailoredCV | None:
    """compile_pdf returned None. No pdflatex: keep the .tex, retry later at
    no LLM cost. pdflatex present: the DOCUMENT is broken and will fail
    identically forever — discard, regenerate next time."""
    if not latex_available():
        return TailoredCV(tex, False)
    logger.warning("the generated CV does not compile — discarding %s, using default CV", tex)
    _discard(tex)
    return None


def _after_compile(tex: Path) -> TailoredCV | None:
    """The cached-.tex path (a machine that gained latex): compile, and enforce
    the one-page rule with nothing left to shrink — an overflowing cached
    document is discarded so the next prepare regenerates under the budget."""
    pdf = compile_pdf(tex)
    if pdf is None:
        return _after_compile_failure(tex)
    pages = page_count(tex)
    if pages is not None and pages > 1:
        logger.warning("the cached CV does not fit one page — discarding %s, using default CV", tex)
        _discard(tex)
        return None
    return TailoredCV(pdf, True)


def _shrunk(selection: CVSelection, pool: CVPool) -> CVSelection | None:
    """The same selection with one less thing on the page, or None when nothing
    can go: the last experience bullet whose experience keeps at least one other
    selected bullet, then the last open-source id."""
    # Only EXPERIENCE bullets are droppable: prose ids only carry a
    # translation, and an open-source id the model misfiled under "bullets"
    # (both pass _known_ids) owns no experience — `bid in owner` skips it.
    owner = {b.id: e.company + e.title for e in pool.experiences for b in e.bullets}
    selected_per_exp: dict[str, int] = {}
    for bid in selection.bullets:
        if bid in owner:
            selected_per_exp[owner[bid]] = selected_per_exp.get(owner[bid], 0) + 1
    for i in range(len(selection.bullets) - 1, -1, -1):
        bid = selection.bullets[i]
        if bid in owner and selected_per_exp[owner[bid]] > 1:
            return replace(selection, bullets=selection.bullets[:i] + selection.bullets[i + 1 :])
    if selection.open_source:
        return replace(selection, open_source=selection.open_source[:-1])
    return None


def _fit_to_one_page(
    out: Path, template: str, selection: CVSelection, pool: CVPool
) -> TailoredCV | None:
    """Render, compile, and drop content from the end until pdflatex reports
    one page. Deterministic and LLM-free: the model already ordered every list
    most-relevant-first, so the tail is what goes."""
    tex = out / "cv.tex"
    current: CVSelection | None = selection
    while current is not None:
        tex.write_text(_MARKER_LINES.sub("", render_cv(template, current, pool)))
        pdf = compile_pdf(tex)
        if pdf is None:
            return _after_compile_failure(tex)
        pages = page_count(tex)
        if pages is None or pages == 1:
            return TailoredCV(pdf, True)
        current = _shrunk(current, pool)
    logger.warning(
        "the generated CV does not fit one page even at minimum — discarding %s, using default CV",
        tex,
    )
    _discard(tex)
    return None


def generated_dir_for(config: dict[str, Any], job_id: int) -> Path:
    base = (config.get("cv") or {}).get("generated_dir")
    root = resolve_under_home(base) if base else resolve_under_home("cv-generated")
    return root / str(job_id)


def _template(config: dict[str, Any], language: str) -> str | None:
    tdir = (config.get("cv") or {}).get("template_dir")
    if not tdir:
        return None
    en = resolve_under_home(tdir) / "cv-template.en.tex"
    pt = resolve_under_home(tdir) / "cv-template.pt.tex"
    if language == "pt":
        if pt.exists():
            return pt.read_text()
        logger.warning("no PT template — rendering the tailored CV in English")
    return en.read_text() if en.exists() else None


async def ensure_tailored_cv(
    job: dict[str, Any],
    config: dict[str, Any],
    profile: dict[str, Any],
    caller: LLMCaller,
) -> TailoredCV | None:
    pool_path = (config.get("cv") or {}).get("pool")
    if not pool_path or not resolve_under_home(pool_path).exists():
        return None
    raw_id = job.get("id")
    if raw_id is None:
        # "never raises" is only total if an id-less job dict degrades too:
        # the cache is keyed on the job id, so there is nothing to generate.
        logger.warning("job has no id — using default CV")
        return None
    out = generated_dir_for(config, int(raw_id))
    # Nothing here is revalidated, and nothing needs to be: a cached cv.tex can
    # only contain escaped model text (render._bullet_text), so recompiling one
    # cannot produce anything its generation did not already produce.
    if (out / "cv.pdf").exists():
        return TailoredCV(out / "cv.pdf", True)
    if (out / "USE_BASE").exists():
        return None
    if (out / "cv.tex").exists():
        return _after_compile(out / "cv.tex")  # a machine that gained latex since

    try:
        pool = load_pool(resolve_under_home(pool_path))
    except PoolError as e:
        logger.warning("cv pool unusable, using default CV — %s", e)
        return None
    en_template = _template(config, "en")
    if en_template is None:
        logger.warning("cv.template_dir has no cv-template.en.tex — using default CV")
        return None
    base_summary = m.group(1) if (m := _BASE_SUMMARY.search(en_template)) else ""
    base_expertise = m.group(1) if (m := _BASE_EXPERTISE.search(en_template)) else ""

    try:
        selection = await decide_cv(job, pool, profile, base_summary, base_expertise, caller)
    except Exception as e:
        if is_spend_limit(e):
            logger.warning("spend limit during cv generation — using default CV")
            return None
        raise
    if selection is None:
        return None  # degraded generation — nothing written, next prepare retries
    out.mkdir(parents=True, exist_ok=True)
    if selection == USE_BASE:
        (out / "USE_BASE").write_text("decided by the generation call\n")
        return None

    template = _template(config, selection.language) or en_template
    return _fit_to_one_page(out, template, selection, pool)
