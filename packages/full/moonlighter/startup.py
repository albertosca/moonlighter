import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from moonlighter.application.answers.cv import configured_cv_path
from moonlighter.core.config import browser_executable, llm_backend, moonlighter_home


@dataclass
class StartupWarning:
    level: Literal["error", "warn"]
    message: str


def validate_startup(
    config: dict[str, Any],
    profile: dict[str, Any],
    cv_path: str | None = None,
) -> list[StartupWarning]:
    """Inspects the environment and returns configuration warnings/errors. Empty list =
    everything ok. 'error' = critical functionality unavailable.
    cv_path: if None, resolves the CV through config exactly as the applier does,
    falling back to <MOONLIGHTER_HOME>/cv.pdf when config maps nothing."""
    configured = configured_cv_path(config)
    cv = cv_path or str(configured or moonlighter_home() / "cv.pdf")
    checks = [
        _check_profile(profile),
        _check_llm_backend(config),
        _check_cv(cv),
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


def _check_llm_backend(config: dict[str, Any]) -> StartupWarning | None:
    """Whichever backend is configured needs its own credential to exist.

    Both arms are checked, from the same resolved backend: guarding only the
    api arm left `llm_backend: cli` without an installed `claude` to fail per
    job, mid-scan, instead of once at startup.
    """
    if llm_backend(config) == "api":
        if os.environ.get("ANTHROPIC_API_KEY"):
            return None
        return StartupWarning(
            "error",
            "llm_backend is 'api' but ANTHROPIC_API_KEY is not in the environment. "
            "scan_and_evaluate and prepare_application will not work. Set the key, or switch to "
            "llm_backend: cli in config.yaml to use your Claude subscription instead.",
        )
    if shutil.which("claude") is not None:
        return None
    return StartupWarning(
        "error",
        "llm_backend is 'cli' but the `claude` CLI was not found on PATH. "
        "scan_and_evaluate and prepare_application will not work. Install Claude Code, or switch to "
        "llm_backend: api in config.yaml and set ANTHROPIC_API_KEY.",
    )


def _check_cv(cv_path: str) -> StartupWarning | None:
    """Missing CV → prepare_application can't name a file to attach for the form's
    upload question."""
    if Path(cv_path).exists():
        return None
    return StartupWarning(
        "warn",
        f"CV file not found at {cv_path}. prepare_application won't be able to point you "
        "at a file to upload. Add your resume there, or set cv.default in config.yaml to "
        "a different path.",
    )


def _check_browser(config: dict[str, Any]) -> StartupWarning | None:
    """Missing browser → LinkedIn scan and browser-based applications don't work."""
    browser_path = browser_executable(config)
    if not browser_path or Path(browser_path).exists():
        return None
    return StartupWarning(
        "warn",
        f"Browser not found at {browser_path}. "
        "LinkedIn scan and browser-based applications will not work. "
        "Install the browser (Chrome/Chromium/Brave) or set browser_path in config.yaml.",
    )
