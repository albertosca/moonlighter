import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from moonlighter.core.config import browser_executable


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
    cv_path: if None, looks in <project_root>/profile/cv.pdf."""
    cv = cv_path or str(Path(__file__).parent.parent / "profile" / "cv.pdf")
    checks = [
        _check_profile(profile),
        _check_api_key(config),
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
        "profile/profile.yaml is empty. "
        "Fill in skills, experience, and criteria for useful LLM evaluations.",
    )


def _check_api_key(config: dict[str, Any]) -> StartupWarning | None:
    """Missing API key → every LLM evaluation returns score=0.0. Only needed for the
    'api' backend; with llm_backend='cli' the `claude` CLI is used instead."""
    if config.get("llm_backend") == "cli" or os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return StartupWarning(
        "error",
        "ANTHROPIC_API_KEY not found in the environment. "
        "scan_and_evaluate and apply_jobs will not work.",
    )


def _check_cv(cv_path: str) -> StartupWarning | None:
    """Missing CV → confirm_apply will fail."""
    if Path(cv_path).exists():
        return None
    return StartupWarning(
        "warn",
        "cv.pdf file not found. confirm_apply will fail. Add your resume to the correct directory.",
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
