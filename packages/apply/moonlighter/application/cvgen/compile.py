"""Compiles the tailored CV .tex with pdflatex — degradation, never a crash.

Two passes (moderncv references), run in the .tex's own directory, bounded by
a timeout. No pdflatex on the machine, or a failed run: the caller keeps the
.tex and tells the operator how to compile it themselves."""

import shutil
import subprocess
from pathlib import Path

from moonlighter.core.log import get_logger

logger = get_logger(__name__)


_PDFLATEX = "pdflatex"


def latex_available() -> bool:
    """Whether this machine can compile at all.

    The caller needs this to read a failed compile correctly: with no pdflatex
    installed a failure says nothing about the document, while with pdflatex
    present it says the document itself is broken.
    """
    return shutil.which(_PDFLATEX) is not None


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
                return None
    except subprocess.TimeoutExpired:
        logger.warning("pdflatex timed out for %s", tex_path)
        return None
    pdf = tex_path.with_suffix(".pdf")
    return pdf if pdf.exists() else None
