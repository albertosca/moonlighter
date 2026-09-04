"""Compiles the tailored-CV pool's structural floor — every experience
rendered by its first pool bullet, the same fallback render_cv falls back
to when nothing is selected for an experience — and reports the real page
count. Run this after editing cv-pool.yaml, not on every prepare_application
(compiling here on every job would double compile cost per job for no
benefit — the floor is a property of the pool, not of any one job).

Backlog: Task 2's renderer fallback guarantees every experience renders at
least its first pool bullet. A pool with enough experiences can make that
floor alone exceed one page — every prepare_application for every job then
burns an LLM call, generates, discovers it cannot shrink below the floor,
and discards to the default CV, silently and repeatedly.

Usage:
    python scripts/check_cv_pool_floor.py
"""

import sys

from moonlighter.application.cvgen.compile import compile_pdf, latex_available, page_count
from moonlighter.application.cvgen.pool import CVPool, PoolError, load_pool
from moonlighter.application.cvgen.render import CVSelection, render_cv
from moonlighter.core.config import load_config, resolve_under_home


def check(pool: CVPool, template: str) -> int | None:
    """The floor's real page count, or None if the check could not run (no
    pdflatex, or the floor itself fails to compile)."""
    if not latex_available():
        return None
    selection = CVSelection(
        language="en",
        summary="",
        technical_expertise="",
        bullets=(),  # nothing selected anywhere — every experience falls
        open_source=(),  # back to its first pool bullet, render_cv's own rule
        translations={},
    )
    tex_text = render_cv(template, selection, pool)
    tex_dir = resolve_under_home("cv-pool-floor-check")
    tex_dir.mkdir(parents=True, exist_ok=True)
    tex = tex_dir / "cv.tex"
    tex.write_text(tex_text)
    pdf = compile_pdf(tex)
    if pdf is None:
        return None
    return page_count(tex)


def main(config: dict) -> int:
    pool_path = (config.get("cv") or {}).get("pool")
    if not pool_path:
        print("No cv.pool configured — nothing to check.")
        return 1
    try:
        pool = load_pool(resolve_under_home(str(pool_path)))
    except PoolError as e:
        print(f"Pool file unusable: {e}")
        return 1
    tdir = (config.get("cv") or {}).get("template_dir")
    if not tdir:
        print("No cv.template_dir configured — nothing to check.")
        return 1
    en_template = resolve_under_home(str(tdir)) / "cv-template.en.tex"
    if not en_template.exists():
        print(f"No cv-template.en.tex found at {en_template}.")
        return 1
    pages = check(pool, en_template.read_text())
    if pages is None:
        print("Could not check: pdflatex not installed, or the floor itself failed to compile.")
        return 1
    if pages == 1:
        print(f"Floor fits: {pages} page.")
        return 0
    print(
        f"Floor overflows: {pages} pages. Every generation for this pool will discard to the "
        "default CV, one wasted LLM call at a time — trim experiences or their bullets."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(load_config()))
