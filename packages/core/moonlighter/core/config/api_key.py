"""The fallback that reads ANTHROPIC_API_KEY from the provider's credential file."""

import os
from pathlib import Path


def anthropic_api_env_file() -> Path:
    """The per-provider credential file: `NAME=value` lines, no quotes, mode 0600."""
    return Path.home() / ".config" / "anthropic" / "api.env"


def fill_api_key_from_file() -> None:
    """Set ANTHROPIC_API_KEY from the provider file when the environment lacks it.

    The environment always wins; a missing or unreadable file is silently
    skipped, so the startup check still reports the absent key.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    try:
        lines = anthropic_api_env_file().read_text().splitlines()
    except OSError, UnicodeDecodeError:
        return
    for line in lines:
        name, separator, value = line.partition("=")
        if separator and name.strip() == "ANTHROPIC_API_KEY" and value.strip():
            os.environ["ANTHROPIC_API_KEY"] = value.strip()
            return
