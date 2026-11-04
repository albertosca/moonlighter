"""Locations: MOONLIGHTER_HOME, the paths resolved under it, and the browser executable."""

import os
from pathlib import Path
from typing import Any


def moonlighter_home() -> Path:
    return Path(os.environ.get("MOONLIGHTER_HOME", "~/.moonlighter")).expanduser()


def resolve_under_home(value: str) -> Path:
    """A config-supplied path, resolved under MOONLIGHTER_HOME when it is relative.

    An absolute path, or a '~'-prefixed one, is honored exactly as given;
    anything else is joined onto moonlighter_home(). Every cv.* config key
    (default, by_company, pool, template_dir, generated_dir) shares this
    convention by delegating here. Callers are expected to reject an empty
    string themselves with a message naming the
    config key -- Path("").expanduser() is ".", a directory that always exists,
    so resolving it silently here would trade a clear "not configured" error for
    a confusing "Is a directory" failure downstream.
    """
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = moonlighter_home() / path
    return path


def learned_blocklist_path() -> Path:
    return moonlighter_home() / "blocklist_learned.yaml"


def browser_executable(config: dict[str, Any]) -> str:
    """Browser executable path.

    Reads 'browser_path'; falls back to the legacy 'brave_path' key when browser_path is empty.
    """
    path: str = config.get("browser_path") or config.get("brave_path", "")
    return path
