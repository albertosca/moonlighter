"""Loading company_list.yaml: the ATS entries to scan, optionally filtered by phase."""

from pathlib import Path
from typing import Any

import yaml

from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.paths import moonlighter_home


def load_company_list(path: str | Path | None = None, phase: str | None = None) -> dict[str, Any]:
    """Load the company list from YAML, optionally filtered by phase.

    company_list.yaml groups entries by ATS and phase:
        greenhouse:
          phase1: [slug, ...]
          phase2: [slug, ...]

    An entry is an ATS slug ("nubank") or, for Recruitee, optionally a full
    custom career domain ("jobs.channable.com").

    Args:
        path: path to company_list.yaml.
        phase: "phase1", "phase2", "phase3", or None for all phases combined.

    Returns:
        dict: {source: [entry, ...]}
    """
    path = Path(path) if path is not None else moonlighter_home() / "company_list.yaml"
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text()) or {}

    result = {source: _select_entries(value, phase) for source, value in raw.items()}
    for source, entries in result.items():
        _require_string_entries(source, entries)

    return result


def _select_entries(value: object, phase: str | None) -> object:
    if isinstance(value, list):
        # Legacy format: flat list without phases
        return value
    if isinstance(value, dict):
        if phase:
            return value.get(phase, [])
        # All phases concatenated
        return _concatenate_phases(value)
    return []


def _concatenate_phases(phases: dict[Any, Any]) -> list[Any]:
    slugs: list[Any] = []
    for slugs_in_phase in phases.values():
        if isinstance(slugs_in_phase, list):
            slugs.extend(slugs_in_phase)
    return slugs


def _require_string_entries(source: object, entries: object) -> None:
    if not isinstance(entries, list):
        # A phase filter selecting a non-list value (e.g. a scalar phase
        # entry) leaves `entries` as that raw value -- a string iterates
        # character-by-character, and every single-char "slug" is a str,
        # so the entry-level check below would silently pass.
        raise ConfigError(
            f"company_list.yaml: source {source!r} did not resolve to a list "
            f"(got {type(entries).__name__}: {entries!r})"
        )
    for entry in entries:
        if not isinstance(entry, str):
            raise ConfigError(
                f"company_list.yaml: source '{source}' has a non-string entry: {entry!r}"
            )
