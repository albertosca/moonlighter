"""Generic entry_points-based plugin discovery.

The public moonlighter repo never names an optional/private extension by import --
instead, the extension declares an entry_point in its own pyproject.toml under a
group this module knows how to enumerate, and gets picked up automatically at
runtime if (and only if) it's installed in the same environment. See
docs/superpowers/specs/2026-07-22-linkedin-plugin-split-design.md for the design
this exists to support.
"""

from importlib.metadata import entry_points
from typing import Any


def discover_entry_points(group: str) -> list[type]:
    """Loads and returns every class registered under `group`. Empty list (never
    raises) if nothing is registered -- the steady state whenever an optional
    plugin package isn't installed."""
    return [ep.load() for ep in entry_points(group=group)]


def discover_entry_points_by_name(group: str) -> dict[str, Any]:
    """Like discover_entry_points, but keyed by each entry point's own name --
    for groups where the caller needs to look an object up by identifier (e.g.
    a platform name), not just get a flat list. Empty dict (never raises) if
    nothing is registered."""
    return {ep.name: ep.load() for ep in entry_points(group=group)}
