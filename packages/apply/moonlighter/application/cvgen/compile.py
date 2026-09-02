"""Compiles the tailored CV .tex with pdflatex — degradation, never a crash.

Two passes (moderncv references), run in the .tex's own directory, bounded by
a timeout. No pdflatex on the machine, or a failed run: the caller keeps the
.tex and tells the operator how to compile it themselves."""

import re
import shutil
import subprocess
from pathlib import Path

from moonlighter.core.log import get_logger

logger = get_logger(__name__)


_PDFLATEX = "pdflatex"
_PAGES = re.compile(r"^Output written on .+\.pdf \((\d+) pages?", re.MULTILINE)


def latex_available() -> bool:
    """Whether this machine can compile at all.

    The caller needs this to read a failed compile correctly: with no pdflatex
    installed a failure says nothing about the document, while with pdflatex
    present it says the document itself is broken.
    """
    return shutil.which(_PDFLATEX) is not None


def _discard_partial(tex_path: Path) -> None:
    """Remove a PDF left behind by a compile that did not succeed.

    pdflatex writes the PDF incrementally, and a timeout SIGKILLs it mid-write
    so it never cleans up after itself — measured at 303KB with a %PDF-1.7
    header and no %%EOF. compile_pdf spawned that process, so it clears the
    remains here: the invariant "a compile that failed leaves no PDF" then
    holds for every caller, present and future, not just the one that
    remembers to check.
    """
    tex_path.with_suffix(".pdf").unlink(missing_ok=True)


def compile_pdf(tex_path: Path, timeout_s: int = 120) -> Path | None:
    pdflatex = shutil.which(_PDFLATEX)
    if pdflatex is None:
        logger.warning("pdflatex not found — keeping %s uncompiled", tex_path)
        return None
    cmd = [pdflatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name]
    try:
        for _ in range(2):  # moderncv needs two passes for internal references
            result = subprocess.run(  # noqa: S603
                cmd, cwd=tex_path.parent, capture_output=True, timeout=timeout_s
            )
            if result.returncode != 0:
                logger.warning("pdflatex failed for %s (rc=%s)", tex_path, result.returncode)
                _discard_partial(tex_path)
                return None
    except subprocess.TimeoutExpired:
        logger.warning("pdflatex timed out for %s", tex_path)
        _discard_partial(tex_path)
        return None
    pdf = tex_path.with_suffix(".pdf")
    return pdf if pdf.exists() else None


def page_count(tex_path: Path) -> int | None:
    """How many pages the last compile produced, read from pdflatex's own log.

    The log is the honest source: it is written by the process that laid the
    pages out. None when there is no log (no compile happened) or no output
    line (the compile died before producing pages).
    """
    log = tex_path.with_suffix(".log")
    if not log.exists():
        return None
    m = _PAGES.search(log.read_text(errors="replace"))
    return int(m.group(1)) if m else None
