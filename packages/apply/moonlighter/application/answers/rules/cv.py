"""Resolves the CV file per company (from config['cv'])."""

from pathlib import Path
from typing import Any

from moonlighter.application.cvgen.latex.compile import looks_like_a_compiled_pdf
from moonlighter.application.cvgen.paths import generated_dir_for
from moonlighter.core.config.paths import resolve_under_home


class CVNotFoundError(Exception):
    """The CV file resolved for the company does not exist on disk."""


def configured_cv_path(config: dict[str, Any], company: str = "") -> Path | None:
    """The CV path config points at, without checking whether it exists.

    Company matching is case-insensitive; falls back to 'default'. Relative
    paths are resolved from MOONLIGHTER_HOME; `~` expands. Returns None when nothing is
    mapped at all.

    Shared with the startup check so that a warning can never name a different
    file from the one the applier would actually upload.
    """
    cv_config = config.get("cv", {}) or {}
    by_company = {
        company_name.lower(): cv_path
        for company_name, cv_path in (cv_config.get("by_company", {}) or {}).items()
    }
    rel = by_company.get((company or "").lower(), cv_config.get("default"))
    if not rel:
        return None
    return resolve_under_home(str(rel))


def resolve_cv_path(company: str, config: dict[str, Any], job_id: int | None = None) -> str:
    """Resolves the CV path to upload.

    The job's own tailored PDF when one exists,
    else the company mapping, else 'default'. Company matching is case-insensitive.
    Relative paths are resolved from MOONLIGHTER_HOME; `~` expands. Raises
    CVNotFoundError if the chosen file does not exist (never silently uploads
    the wrong CV).
    """
    if job_id is not None:
        tailored = generated_dir_for(config, job_id) / "cv.pdf"
        # exists() alone would upload a stranded partial-write (round-6
        # finding) or try to upload a directory; degrades the same way a
        # missing file already does — fall through to the company/default CV.
        if looks_like_a_compiled_pdf(tailored):
            return str(tailored)

    path = configured_cv_path(config, company)
    if path is None:
        raise CVNotFoundError(
            f"No CV mapped for '{company}' and no 'cv.default' in config. Check config.yaml."
        )
    if not path.exists():
        raise CVNotFoundError(
            f"CV for '{company}' not found at {path}. Check the 'cv' mapping in config."
        )
    return str(path)
