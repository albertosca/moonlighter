"""Startup checks: configuration problems reported once at boot, not per call mid-scan."""

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from moonlighter.application.answers.rules.cv import configured_cv_path
from moonlighter.core.config.backends import llm_backend
from moonlighter.core.config.paths import browser_executable, moonlighter_home
from moonlighter.core.llm.codex import codex_executable
from moonlighter.core.llm.cursor import cursor_executable
from moonlighter.discovery.evaluation.regional_eligibility import LOCATION_PRECEDENCES


@dataclass
class StartupWarning:
    level: Literal["error", "warn"]
    message: str


def validate_startup(
    config: dict[str, Any],
    profile: dict[str, Any],
    cv_path: str | None = None,
) -> list[StartupWarning]:
    """Inspect the environment and return configuration warnings and errors.

    An empty list means everything is ok; 'error' means critical functionality is
    unavailable. `cv_path`, when None, resolves the CV through config exactly as the
    applier does, falling back to <MOONLIGHTER_HOME>/cv.pdf when config maps nothing.
    """
    configured = configured_cv_path(config)
    resume_path = cv_path or str(configured or moonlighter_home() / "cv.pdf")
    checks = [
        _check_profile(profile),
        _check_location_precedence(profile),
        _check_llm_backend(config),
        _check_cv(resume_path),
        _check_browser(config),
    ]
    return [warning for warning in checks if warning is not None]


def _check_profile(profile: dict[str, Any]) -> StartupWarning | None:
    """Empty profile → useless LLM evaluations."""
    if profile:
        return None
    return StartupWarning(
        "warn",
        f"{moonlighter_home() / 'profile.yaml'} is empty. "
        "Fill in skills, experience, and criteria for useful LLM evaluations.",
    )


def _check_location_precedence(profile: dict[str, Any]) -> StartupWarning | None:
    """An unknown value silently meant "specific" (2026-09-29 review)."""
    criteria = profile.get("criteria") or {}
    value = criteria.get("location_precedence") if isinstance(criteria, dict) else None
    if value is None or value in LOCATION_PRECEDENCES:
        return None
    return StartupWarning(
        "warn",
        f"profile.yaml: criteria.location_precedence is {value!r}; it must be one of "
        f'{", ".join(LOCATION_PRECEDENCES)}. Scoring uses "specific" until it is fixed.',
    )


_BACKEND_CREDENTIALS: dict[str, tuple[Callable[[], bool], str]] = {
    "api": (
        lambda: bool(os.environ.get("ANTHROPIC_API_KEY")),
        (
            "llm_backend is 'api' but ANTHROPIC_API_KEY is not in the environment "
            "nor in ~/.config/anthropic/api.env. "
            "scan_and_evaluate and prepare_application will not work. Set the key, or switch to "
            "llm_backend: cli in config.yaml to use your Claude subscription instead."
        ),
    ),
    "cursor": (
        lambda: cursor_executable() is not None,
        (
            "llm_backend is 'cursor' but the `agent` CLI was not found on PATH. "
            "scan_and_evaluate and prepare_application will not work. "
            "Install the Cursor CLI and run `agent login`."
        ),
    ),
    "codex": (
        lambda: codex_executable() is not None,
        (
            "llm_backend is 'codex' but the `codex` CLI was not found on PATH. "
            "scan_and_evaluate and prepare_application will not work. "
            "Install the Codex CLI and run `codex login` with your ChatGPT account."
        ),
    ),
    "cli": (
        lambda: shutil.which("claude") is not None,
        (
            "llm_backend is 'cli' but the `claude` CLI was not found on PATH. "
            "scan_and_evaluate and prepare_application will not work. Install Claude Code, or switch to "
            "llm_backend: api in config.yaml and set ANTHROPIC_API_KEY."
        ),
    ),
}


def _check_llm_backend(config: dict[str, Any]) -> StartupWarning | None:
    """Whichever backend is configured needs its own credential to exist.

    Every backend is checked, from the same resolved backend: guarding only the
    api one left `llm_backend: cli` without an installed `claude` to fail per
    job, mid-scan, instead of once at startup. Each check looks its function up
    when it runs, so a test that patches `cursor_executable` or `shutil.which`
    in this module still reaches it.
    """
    is_available, message = _BACKEND_CREDENTIALS[llm_backend(config)]
    if is_available():
        return None
    return StartupWarning("error", message)


def _check_cv(cv_path: str) -> StartupWarning | None:
    """Missing CV: prepare_application can't name a file to attach for the form's upload question."""
    if Path(cv_path).exists():
        return None
    return StartupWarning(
        "warn",
        f"CV file not found at {cv_path}. prepare_application won't be able to point you "
        "at a file to upload. Add your resume there, or set cv.default in config.yaml to "
        "a different path.",
    )


def _check_browser(config: dict[str, Any]) -> StartupWarning | None:
    """Missing browser: a browser-based scan extension (e.g. LinkedIn) won't work.

    moonlighter itself never opens a browser (see DISCLAIMER.md).
    """
    browser_path = browser_executable(config)
    if not browser_path or Path(browser_path).exists():
        return None
    return StartupWarning(
        "warn",
        f"Browser not found at {browser_path}. "
        "A browser-based scan extension, if installed, will not work. "
        "Install the browser (Chrome/Chromium/Brave) or set browser_path in config.yaml.",
    )
