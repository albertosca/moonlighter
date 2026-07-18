"""Resolves the CV file per company (from config['cv'])."""

from pathlib import Path
from typing import Any

from gauntler.core.config import gauntler_home


class CVNotFoundError(Exception):
    """The CV file resolved for the company does not exist on disk."""


def resolve_cv_path(company: str, config: dict[str, Any]) -> str:
    """
    Resolves the CV path for the company from config['cv'].
    Company matching is case-insensitive. Falls back to 'default' when there's
    no mapping. Relative paths are resolved from GAUNTLER_HOME.
    Raises CVNotFoundError if the chosen file does not exist (never silently
    uploads the wrong CV).
    """
    cv_cfg = config.get("cv", {}) or {}
    by_company = {k.lower(): v for k, v in (cv_cfg.get("by_company", {}) or {}).items()}
    rel = by_company.get((company or "").lower(), cv_cfg.get("default"))
    if not rel:
        raise CVNotFoundError(
            f"No CV mapped for '{company}' and no 'cv.default' in config. Check config.yaml."
        )
    path = Path(rel)
    if not path.is_absolute():
        path = gauntler_home() / path
    if not path.exists():
        raise CVNotFoundError(
            f"CV for '{company}' not found at {path}. Check the 'cv' mapping in config."
        )
    return str(path)
