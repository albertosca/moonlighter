"""Generic entry_points-based plugin discovery.

The public moonlighter repo never names an optional/private extension by import --
instead, the extension declares an entry_point in its own pyproject.toml under a
group this module knows how to enumerate, and gets picked up automatically at
runtime if (and only if) it's installed in the same environment. See
docs/superpowers/specs/2026-07-22-linkedin-plugin-split-design.md for the design
this exists to support.
"""

from importlib.metadata import entry_points


def discover_entry_points(group: str) -> list[type]:
    """Loads and returns every class registered under `group`. Empty list (never
    raises) if nothing is registered -- the steady state whenever an optional
    plugin package isn't installed."""
    return [ep.load() for ep in entry_points(group=group)]
