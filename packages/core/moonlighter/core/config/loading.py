"""Loading config.yaml (merged onto the defaults) and profile.yaml from MOONLIGHTER_HOME."""

from pathlib import Path
from typing import Any

import yaml

from moonlighter.core.config.api_key import fill_api_key_from_file
from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.config.paths import learned_blocklist_path, moonlighter_home

_PATH_KEYS = ("browser_session_dir", "screenshots_dir")


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load configuration from YAML file, merging with defaults.

    Expands home directory (~) paths for designated path keys.

    Args:
        config_path: Path to config.yaml file

    Returns:
        dict with merged config (defaults + overrides)
    """
    config_path = (
        Path(config_path) if config_path is not None else moonlighter_home() / "config.yaml"
    )
    home = moonlighter_home()
    config: dict[str, Any] = {
        **DEFAULTS,
        "browser_session_dir": str(home / "browser-session"),
        "screenshots_dir": str(home / "screenshots"),
    }
    user = _read_user_config(config_path)
    _merge_user_config(config, user)
    if config.get("llm_backend") == "codex" and "eval_model" not in user:
        # The shipped eval_model is a Claude id; one model to name is enough for a
        # user who did not pick a cheaper one for evaluations.
        config["eval_model"] = config["llm_model"]
    for key in _PATH_KEYS:
        config[key] = str(Path(config[key]).expanduser())

    _merge_learned_blocklist(config)

    # Only the api backend needs the key. cli strips it so `claude -p` bills the
    # subscription; cursor and codex authenticate with their own login and never read it.
    if config.get("llm_backend") == "api":
        fill_api_key_from_file()
    return config


def _read_user_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    user: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
    return user


def _merge_user_config(config: dict[str, Any], user: dict[str, Any]) -> None:
    for key, value in user.items():
        # A dict-valued default (e.g. email:) merges key-by-key: a user
        # overriding one sub-key must not silently drop the siblings'
        # defaults, which is how a partial email: block used to lose
        # token_path and trip the credentials guard on valid setups.
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **value}
        else:
            config[key] = value


def _merge_learned_blocklist(config: dict[str, Any]) -> None:
    """Merge learned blocklist (blocklist_learned.yaml) into title_blocklist."""
    learned = learned_blocklist_path()
    if learned.exists():
        data = yaml.safe_load(learned.read_text()) or {}
        learned_patterns = data.get("title_blocklist", [])
        if learned_patterns:
            manual = config.get("title_blocklist", [])
            merged = list(dict.fromkeys(manual + learned_patterns))  # dedup, manual first
            config["title_blocklist"] = merged


def load_profile(profile_path: str | Path | None = None) -> dict[str, Any]:
    """Load profile from YAML file.

    Args:
        profile_path: Path to profile.yaml file

    Returns:
        dict with profile data (skills, experience, preferences, criteria, etc.)
    """
    profile_path = (
        Path(profile_path) if profile_path is not None else moonlighter_home() / "profile.yaml"
    )
    return yaml.safe_load(profile_path.read_text()) or {}
