import os
from pathlib import Path
from typing import Any

import yaml


def gauntler_home() -> Path:
    return Path(os.environ.get("GAUNTLER_HOME", "~/.gauntler")).expanduser()


def _learned_blocklist_path() -> Path:
    return gauntler_home() / "blocklist_learned.yaml"


def browser_executable(config: dict[str, Any]) -> str:
    """Browser executable path. Reads 'browser_path'; falls back to the legacy
    'brave_path' key when browser_path is empty."""
    path: str = config.get("browser_path") or config.get("brave_path", "")
    return path


# Sentinel for a form field the LLM did not (or should not) answer, stopping in front
# of the operator instead of guessing. This is a constant, not a config key: every
# producer (base.py, work_auth.py) and every consumer (service.py's submission gate,
# greenhouse.py's skip list) must agree on the exact same string, or an unanswered
# field silently degrades into whatever literal text was configured — typed into a
# real form field and submitted, with no operator stop. There is no way to make that
# divergence safe by configuration; the fix is for the string to have exactly one
# source of truth.
NEEDS_REVIEW_SENTINEL = "__NEEDS_REVIEW__"


DEFAULTS = {
    # Browser executable path (Chrome/Chromium/Brave). Empty by default:
    # set browser_path in config.yaml. Accepts brave_path (legacy) as a fallback.
    "browser_path": "",
    "score_threshold": 6.5,
    "llm_model": "claude-sonnet-4-6",
    "eval_model": "claude-haiku-4-5-20251001",
    "slow_mo_ms": 300,
    "title_blocklist": [],
    # Max parallel LLM evaluations in the scan. Bounds the token burst and the
    # waste after the spend-limit (in-flight siblings). With batching (scan_batch_size),
    # this is the number of BATCHES in parallel. Effective concurrency = scan_concurrency × scan_batch_size.
    "scan_concurrency": 5,
    # Jobs evaluated per LLM call. The profile is sent once per batch, cutting
    # re-transmission by a factor of K. 1 disables batching (1 job per call).
    "scan_batch_size": 5,
    # CV per company. Paths relative to GAUNTLER_HOME; case-insensitive match.
    # 'default' used when the company has no entry. Can be overridden in the
    # local config.yaml. If the chosen file doesn't exist, confirm_apply aborts.
    "cv": {
        "default": "",
        "by_company": {},
    },
    # Country-dependent work authorization. The candidate is authorized to work
    # only in their citizenship country. When the job's country cannot be
    # confidently inferred, the field becomes __NEEDS_REVIEW__ (manual decision — never a guess).
    "work_authorization": {
        "citizenship_country": "",
        "authorized_answer": "Yes",
        "not_authorized_answer": "No",
    },
}

_PATH_KEYS = ("browser_session_dir", "screenshots_dir")


class ConfigError(Exception):
    """Raised when config.yaml has an unknown key or a value of the wrong type."""


# (type, ...) — a tuple of acceptable types; bool is excluded from int keys explicitly.
_INT = (int,)
_NUM = (int, float)

# Top-level key -> acceptable types. Nested dict blocks use a sub-schema below.
_CONFIG_SCHEMA: dict[str, tuple[type, ...]] = {
    "browser_path": (str,),
    "brave_path": (str,),
    "browser_session_dir": (str,),
    "screenshots_dir": (str,),
    "score_threshold": _NUM,
    "slow_mo_ms": _INT,
    "scan_concurrency": _INT,
    "scan_batch_size": _INT,
    "llm_model": (str,),
    "eval_model": (str,),
    "llm_backend": (str,),
    "title_blocklist": (list,),
    "cv": (dict,),
    "work_authorization": (dict,),
    "email": (dict,),
}

_CV_SCHEMA: dict[str, tuple[type, ...]] = {"default": (str,), "by_company": (dict,)}
_WORK_AUTH_SCHEMA: dict[str, tuple[type, ...]] = {
    "citizenship_country": (str,),
    "authorized_answer": (str,),
    "not_authorized_answer": (str,),
}
_EMAIL_SCHEMA: dict[str, tuple[type, ...]] = {
    "address": (str,),
    "credentials_path": (str,),
    "token_path": (str,),
    "processed_label": (str,),
    "mark_processed": (bool,),
    "interview_stages": (list,),
}
_NESTED_SCHEMAS = {
    "cv": _CV_SCHEMA,
    "work_authorization": _WORK_AUTH_SCHEMA,
    "email": _EMAIL_SCHEMA,
}


def _check_type(key: str, value: Any, types: tuple[type, ...]) -> None:
    # bool is a subclass of int; reject it where int is required (and bool is not listed).
    if isinstance(value, bool) and bool not in types:
        raise ConfigError(
            f"config key '{key}' must be {', '.join(t.__name__ for t in types)}, got bool"
        )
    if not isinstance(value, types):
        raise ConfigError(
            f"config key '{key}' must be {', '.join(t.__name__ for t in types)}, "
            f"got {type(value).__name__}"
        )


def validate_config(config: dict[str, Any]) -> None:
    """Strict, closed-schema validation. Raises ConfigError on the first unknown key or
    wrong-typed value (naming the key). Runs after the DEFAULTS merge, so an omitted key is
    filled by defaults and never fails here — only wrong types and unknown extras fail."""
    for key, value in config.items():
        if key not in _CONFIG_SCHEMA:
            raise ConfigError(f"unknown config key '{key}'")
        _check_type(key, value, _CONFIG_SCHEMA[key])
        sub_schema = _NESTED_SCHEMAS.get(key)
        if sub_schema is not None:
            for sub_key, sub_value in value.items():
                if sub_key not in sub_schema:
                    raise ConfigError(f"unknown config key '{key}.{sub_key}'")
                _check_type(f"{key}.{sub_key}", sub_value, sub_schema[sub_key])


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """
    Load configuration from YAML file, merging with defaults.

    Expands home directory (~) paths for designated path keys.

    Args:
        config_path: Path to config.yaml file

    Returns:
        dict with merged config (defaults + overrides)
    """
    config_path = Path(config_path) if config_path is not None else gauntler_home() / "config.yaml"
    home = gauntler_home()
    config: dict[str, Any] = {
        **DEFAULTS,
        "browser_session_dir": str(home / "browser-session"),
        "screenshots_dir": str(home / "screenshots"),
    }
    if config_path.exists():
        user = yaml.safe_load(config_path.read_text()) or {}
        config.update(user)
    for key in _PATH_KEYS:
        config[key] = str(Path(config[key]).expanduser())

    # Merge learned blocklist (blocklist_learned.yaml) into title_blocklist
    learned = _learned_blocklist_path()
    if learned.exists():
        data = yaml.safe_load(learned.read_text()) or {}
        learned_patterns = data.get("title_blocklist", [])
        if learned_patterns:
            manual = config.get("title_blocklist", [])
            merged = list(dict.fromkeys(manual + learned_patterns))  # dedup, manual first
            config["title_blocklist"] = merged

    return config


def load_profile(profile_path: str | Path | None = None) -> dict[str, Any]:
    """
    Load profile from YAML file.

    Args:
        profile_path: Path to profile.yaml file

    Returns:
        dict with profile data (skills, experience, preferences, criteria, etc.)
    """
    profile_path = (
        Path(profile_path) if profile_path is not None else gauntler_home() / "profile.yaml"
    )
    return yaml.safe_load(profile_path.read_text()) or {}


def load_company_list(path: str | Path | None = None, phase: str | None = None) -> dict[str, Any]:
    """Load company list from YAML file, optionally filtered by phase.

    O company_list.yaml organiza slugs por ATS e fase:
        greenhouse:
          phase1: [slug, ...]
          phase2: [slug, ...]

    Args:
        path: Path to company_list.yaml file
        phase: "phase1", "phase2", "phase3", ou None para todas as fases.

    Returns:
        dict: {source: [slug, ...]} (e.g., {"greenhouse": ["nubank", "ifoodcarreiras"]})
    """
    path = Path(path) if path is not None else gauntler_home() / "company_list.yaml"
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text()) or {}

    result = {}
    for source, value in raw.items():
        if isinstance(value, list):
            # Legacy format: flat list without phases
            result[source] = value
        elif isinstance(value, dict):
            if phase:
                result[source] = value.get(phase, [])
            else:
                # Todas as fases concatenadas
                slugs = []
                for slugs_in_phase in value.values():
                    if isinstance(slugs_in_phase, list):
                        slugs.extend(slugs_in_phase)
                result[source] = slugs
        else:
            result[source] = []
    return result


_HARDEN_FILES = ("gauntler.db", "profile.yaml", "config.yaml", "app.log", "blocklist_learned.yaml")
_HARDEN_DIRS = ("browser-session", "screenshots")


def harden_permissions() -> list[str]:
    """Set 0600/0700 on the sensitive files/subdirectories under ~/.gauntler
    (S-07): gauntler.db, profile.yaml and config.yaml carry full PII;
    browser-session/ holds cookies equivalent to LinkedIn credentials.
    Best-effort and never raises — a permission error becomes a warning,
    since the server must stay up even on an unusual filesystem/ACL setup."""
    home = gauntler_home()
    warnings: list[str] = []
    for name in _HARDEN_FILES:
        path = home / name
        if path.exists():
            try:
                path.chmod(0o600)
            except OSError as e:
                warnings.append(f"could not restrict permissions on {path}: {e}")
    for name in _HARDEN_DIRS:
        path = home / name
        if path.exists():
            try:
                path.chmod(0o700)
            except OSError as e:
                warnings.append(f"could not restrict permissions on {path}: {e}")
    return warnings
