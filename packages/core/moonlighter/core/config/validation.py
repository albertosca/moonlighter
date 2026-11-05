"""Closed-schema validation of a loaded config: unknown keys and wrong types fail by name."""

from typing import Any

from moonlighter.core.config.backends import llm_backend, require_codex_models
from moonlighter.core.config.errors import ConfigError

# (type, ...) — a tuple of acceptable types; bool is excluded from int keys explicitly.
_INTEGER = (int,)
_NUMBER = (int, float)

# Top-level key -> acceptable types. Nested dict blocks use a sub-schema below.
_CONFIG_SCHEMA: dict[str, tuple[type, ...]] = {
    "browser_path": (str,),
    "brave_path": (str,),
    "browser_session_dir": (str,),
    "screenshots_dir": (str,),
    "score_threshold": _NUMBER,
    "slow_mo_ms": _INTEGER,
    "scan_concurrency": _INTEGER,
    "scan_batch_size": _INTEGER,
    "llm_model": (str,),
    "eval_model": (str,),
    "llm_backend": (str,),
    "cursor_model": (str,),
    "llm_timeout_seconds": _NUMBER,
    "title_blocklist": (list,),
    "cv": (dict,),
    "work_authorization": (dict,),
    "email": (dict,),
    "scan_gupy": (bool,),
    "scan_remoteok": (bool,),
    "scan_remotive": (bool,),
    "remotive_category": (str,),
    "scan_wwr": (bool,),
    "wwr_category": (str,),
    "scan_hn_whoishiring": (bool,),
    "portal_max_age_days": _INTEGER,
    "answer_bank_max_age_days": (*_INTEGER, type(None)),  # null disables expiry
}

_CV_SCHEMA: dict[str, tuple[type, ...]] = {
    "default": (str,),
    "by_company": (dict,),
    # Tailored-CV feature (specs/2026-08-25-tailored-cv-design.md). All three
    # optional: the feature activates only when `pool` names an existing file.
    "pool": (str,),
    "template_dir": (str,),
    "generated_dir": (str,),
}
_WORK_AUTHORIZATION_SCHEMA: dict[str, tuple[type, ...]] = {
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
    "archive_ref_matched": (bool,),
    "archive_all_classified": (bool,),
    "lookback_days": (int,),
    "interview_stages": (list,),
}
_NESTED_SCHEMAS = {
    "cv": _CV_SCHEMA,
    "work_authorization": _WORK_AUTHORIZATION_SCHEMA,
    "email": _EMAIL_SCHEMA,
}


def validate_config(config: dict[str, Any]) -> None:
    """Strict, closed-schema validation.

    Raises ConfigError on the first unknown key or wrong-typed value (naming the key). Runs
    after the DEFAULTS merge, so an omitted key is filled by defaults and never fails here —
    only wrong types and unknown extras fail.
    """
    for key, value in config.items():
        _validate_key(config, key, value)
    if config.get("llm_backend") == "codex":
        require_codex_models(config)


def _validate_key(config: dict[str, Any], key: str, value: Any) -> None:
    if key not in _CONFIG_SCHEMA:
        raise ConfigError(f"unknown config key '{key}'")
    _check_type(key, value, _CONFIG_SCHEMA[key])
    if key == "llm_backend":
        llm_backend(config)
    if key == "llm_timeout_seconds" and value <= 0:
        # Zero would kill every call before it answered — reading like a
        # broken CLI instead of the config mistake it is.
        raise ConfigError(f"config key 'llm_timeout_seconds' must be positive, got {value}")
    sub_schema = _NESTED_SCHEMAS.get(key)
    if sub_schema is not None:
        _validate_nested_block(key, value, sub_schema)


def _validate_nested_block(
    key: str, block: dict[str, Any], sub_schema: dict[str, tuple[type, ...]]
) -> None:
    for sub_key, sub_value in block.items():
        if sub_key not in sub_schema:
            raise ConfigError(f"unknown config key '{key}.{sub_key}'")
        _check_type(f"{key}.{sub_key}", sub_value, sub_schema[sub_key])
        if key == "email" and sub_key == "lookback_days" and sub_value <= 0:
            # Gmail's newer_than:0d matches zero messages (verified live) —
            # a non-positive value silently disables the sync forever, reading
            # exactly like an empty mailbox instead of a config mistake.
            raise ConfigError(f"config key 'email.lookback_days' must be positive, got {sub_value}")


def _check_type(key: str, value: Any, types: tuple[type, ...]) -> None:
    # bool is a subclass of int; reject it where int is required (and bool is not listed).
    if isinstance(value, bool) and bool not in types:
        raise ConfigError(f"config key '{key}' must be {_describe_types(types)}, got bool")
    if not isinstance(value, types):
        raise ConfigError(
            f"config key '{key}' must be {_describe_types(types)}, got {type(value).__name__}"
        )


def _describe_types(types: tuple[type, ...]) -> str:
    return ", ".join(allowed.__name__ for allowed in types)
