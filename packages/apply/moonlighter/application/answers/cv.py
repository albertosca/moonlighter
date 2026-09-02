"""Resolves the CV file per company (from config['cv'])."""

from pathlib import Path
from typing import Any

from moonlighter.core.config import resolve_under_home


class CVNotFoundError(Exception):
    """The CV file resolved for the company does not exist on disk."""


def configured_cv_path(config: dict[str, Any], company: str = "") -> Path | None:
    """
    The CV path config points at, without checking whether it exists.
    Company matching is case-insensitive; falls back to 'default'. Relative
    paths are resolved from MOONLIGHTER_HOME; `~` expands. Returns None when nothing is
    mapped at all.

    Shared with the startup check so that a warning can never name a different
    file from the one the applier would actually upload.
    """
    cv_cfg = config.get("cv", {}) or {}
    by_company = {k.lower(): v for k, v in (cv_cfg.get("by_company", {}) or {}).items()}
    rel = by_company.get((company or "").lower(), cv_cfg.get("default"))
    if not rel:
        return None
    return resolve_under_home(str(rel))


def resolve_cv_path(company: str, config: dict[str, Any], job_id: int | None = None) -> str:
    """
    Resolves the CV path to upload: the job's own tailored PDF when one exists,
    else the company mapping, else 'default'. Company matching is case-insensitive.
    Relative paths are resolved from MOONLIGHTER_HOME. Raises CVNotFoundError if
    the chosen file does not exist (never silently uploads the wrong CV).
    """
    if job_id is not None:
        from moonlighter.application.cvgen.service import generated_dir_for

        tailored = generated_dir_for(config, job_id) / "cv.pdf"
        if tailored.exists():
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
