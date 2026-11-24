"""Loading config.yaml (merged onto the defaults) and profile.yaml from MOONLIGHTER_HOME."""

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml

from moonlighter.core.config.api_key import fill_api_key_from_file
from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.config.model import Config
from moonlighter.core.config.paths import learned_blocklist_path, moonlighter_home
from moonlighter.core.config.validation import validate_config

_PATH_KEYS = ("browser_session_dir", "screenshots_dir")


def build_config(user: Mapping[str, Any]) -> Config:
    """The validated config for a user mapping: the defaults merged under it, no file read.

    What tests call: the same shape production builds, with no YAML, learned blocklist
    or API key involved. Raises ConfigError naming the first bad key.
    """
    config = _merge(user)
    validate_config(config)
    return cast("Config", config)


def load_config(config_path: str | Path | None = None) -> Config:
    """config.yaml merged onto the defaults, the learned blocklist added, then validated.

    Raises ConfigError naming the first bad key, before anything reads the API key file.
    """
    config_path = (
        Path(config_path) if config_path is not None else moonlighter_home() / "config.yaml"
    )
    config = _merge(_read_user_config(config_path))
    _merge_learned_blocklist(config)
    validate_config(config)
    # Only the api backend needs the key. cli strips it so `claude -p` bills the
    # subscription; cursor and codex authenticate with their own login and never read it.
    if config["llm_backend"] == "api":
        fill_api_key_from_file()
    return cast("Config", config)


def _merge(user: Mapping[str, Any]) -> dict[str, Any]:
    home = moonlighter_home()
    config: dict[str, Any] = {
        # A deep copy: a loaded config used to share its nested blocks with DEFAULTS,
        # so a learned interview stage leaked into every later load (probe, 2026-11-24).
        **copy.deepcopy(DEFAULTS),
        "browser_session_dir": str(home / "browser-session"),
        "screenshots_dir": str(home / "screenshots"),
    }
    # Copied too: a caller's overrides must not change when the built config does.
    _merge_user_config(config, copy.deepcopy(dict(user)))
    if config.get("llm_backend") == "codex" and "eval_model" not in user:
        # The shipped eval_model is a Claude id; one model to name is enough for a
        # user who did not pick a cheaper one for evaluations.
        config["eval_model"] = config["llm_model"]
    for key in _PATH_KEYS:
        config[key] = str(Path(config[key]).expanduser())
    return config


def _read_user_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    user: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
    return user


def _merge_user_config(config: dict[str, Any], user: Mapping[str, Any]) -> None:
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
