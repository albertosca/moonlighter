"""Compiles the tailored-CV pool's structural floor and reports the real page count.

The floor is every experience rendered by its first pool bullet, the same fallback render_cv uses when nothing is selected for an experience. Run this after editing cv-pool.yaml, not on every prepare_application: compiling here on every job would double the compile cost per job for no benefit, because the floor is a property of the pool, not of any one job.

Backlog: the renderer's fallback guarantees every experience renders at least its first pool bullet. A pool with enough experiences can make that floor alone exceed one page, and every prepare_application for every job then burns an LLM call, generates, discovers it cannot shrink below the floor, and discards to the default CV, silently and repeatedly.

Usage:
    python scripts/check_cv_pool_floor.py
"""

import sys
from typing import Any

from moonlighter.application.cvgen.latex.compile import compile_pdf, latex_available, page_count
from moonlighter.application.cvgen.latex.render import CVSelection, render_cv
from moonlighter.application.cvgen.pool.loader import CVPool, PoolError, load_pool
from moonlighter.core.config.loading import load_config
from moonlighter.core.config.paths import resolve_under_home


def check(pool: CVPool, template: str) -> int | None:
    """The floor's real page count, or None when the check could not run.

    It cannot run without pdflatex, and it gives no count when the floor itself fails to compile.
    """
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
    tex_source = render_cv(template, selection, pool)
    tex_directory = resolve_under_home("cv-pool-floor-check")
    tex_directory.mkdir(parents=True, exist_ok=True)
    tex_path = tex_directory / "cv.tex"
    tex_path.write_text(tex_source)
    pdf = compile_pdf(tex_path)
    if pdf is None:
        return None
    return page_count(tex_path)


def _load_pool(config: dict[str, Any]) -> CVPool | None:
    pool_path = (config.get("cv") or {}).get("pool")
    if not pool_path:
        print("No cv.pool configured — nothing to check.")
        return None
    try:
        return load_pool(resolve_under_home(str(pool_path)))
    except PoolError as error:
        print(f"Pool file unusable: {error}")
        return None


def _load_template(config: dict[str, Any]) -> str | None:
    template_directory = (config.get("cv") or {}).get("template_dir")
    if not template_directory:
        print("No cv.template_dir configured — nothing to check.")
        return None
    english_template_path = resolve_under_home(str(template_directory)) / "cv-template.en.tex"
    if not english_template_path.exists():
        print(f"No cv-template.en.tex found at {english_template_path}.")
        return None
    return english_template_path.read_text()


def _report(pages: int) -> int:
    if pages == 1:
        print(f"Floor fits: {pages} page.")
        return 0
    print(
        f"Floor overflows: {pages} pages. Every generation for this pool will discard to the "
        "default CV, one wasted LLM call at a time — trim experiences or their bullets."
    )
    return 1


def main(config: dict[str, Any]) -> int:
    pool = _load_pool(config)
    if pool is None:
        return 1
    template = _load_template(config)
    if template is None:
        return 1
    pages = check(pool, template)
    if pages is None:
        print("Could not check: pdflatex not installed, or the floor itself failed to compile.")
        return 1
    return _report(pages)


if __name__ == "__main__":
    sys.exit(main(load_config()))
