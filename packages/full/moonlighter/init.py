"""Interactive first-run setup: writes config.yaml and registers or prints the MCP server.

Replaces the manual `cp config.example.yaml ~/.moonlighter/` + hand-edit flow, which was the
single largest source of setup friction for a new user.
"""

import os
import shutil
from pathlib import Path

import yaml

from moonlighter.core.config.backends import llm_backend
from moonlighter.core.config.validation import validate_config
from moonlighter.opencode_registration import (
    Registration,
    opencode_config_path,
    register_in_opencode,
    registration_snippet,
)

# Backends whose CLI is handed llm_model / eval_model, so the wizard asks for both.
_MODEL_BACKENDS = ("codex", "opencode")
_CLAUDE_REGISTRATION = (
    '  claude mcp add-json --scope user moonlighter \'{"command":"uvx","args":["moonlighter"]}\''
)

# Common install locations, most-preferred first. Chromium-family only -- moonlighter drives a
# real browser profile so the user's logged-in sessions are reusable.
_BROWSER_CANDIDATES = (
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)


def detect_browser() -> str | None:
    """First browser executable that exists on disk, or None."""
    for candidate in _BROWSER_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def run_init(home: Path, answers: dict[str, str]) -> Path:
    """Write config.yaml into `home` from the wizard's answers.

    Refuses to overwrite an existing config -- clobbering a user's real
    configuration is not recoverable.
    """
    # Validate before touching the filesystem: a wizard that writes a config the
    # next boot rejects sends the user to fix a file it just walked them through.
    backend = llm_backend({"llm_backend": answers["llm_backend"]})
    models: dict[str, str] = {}
    if backend in _MODEL_BACKENDS:
        model = answers.get("llm_model", "").strip()
        eval_model = answers.get("eval_model", "").strip() or model
        models = {"llm_model": model, "eval_model": eval_model}
        validate_config({"llm_backend": backend, **models})

    config_path = home / "config.yaml"
    if config_path.exists():
        raise FileExistsError(
            f"{config_path} already exists. Edit it directly, or move it aside to re-run init."
        )
    home.mkdir(parents=True, exist_ok=True)
    home.chmod(0o700)

    config = {
        "browser_path": answers["browser_path"],
        "llm_backend": answers["llm_backend"],
        **models,
        "work_authorization": {
            "citizenship_country": answers["citizenship_country"],
            "authorized_answer": "Yes",
            "not_authorized_answer": "No",
        },
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    config_path.chmod(0o600)
    return config_path


def next_steps(backend: str, registration: Registration | None) -> list[str]:
    """What to run after the config is written, for the client the person uses."""
    if backend == "opencode":
        # The LLM backend does not pick the MCP client: opencode first, Claude Code still offered.
        lines = _opencode_lines(backend, registration) + _claude_as_client_lines()
    else:
        lines = _claude_lines(registration) + _opencode_lines(backend, registration)
    lines.append(
        "Once connected, ask your agent to run get_pipeline to check your setup for problems."
    )
    return lines


def _claude_lines(registration: Registration | None) -> list[str]:
    lines = ["Then register the MCP server:", "", _CLAUDE_REGISTRATION, ""]
    if registration is None:
        lines += [
            'Using a different MCP client? Register uvx / ["moonlighter"] with its own mechanism.',
            "",
        ]
    return lines


def _claude_as_client_lines() -> list[str]:
    return [
        "Using Claude Code as your MCP client too? Register it there with:",
        "",
        _CLAUDE_REGISTRATION,
        "",
    ]


def _opencode_lines(backend: str, registration: Registration | None) -> list[str]:
    if registration is not None and registration.written:
        return [
            (
                f"Registered in {registration.path}. Start opencode and run "
                "`opencode mcp list`: it should show `✓ moonlighter connected`."
            ),
            "",
        ]
    if registration is None:
        if backend != "opencode":
            return []
        return [f"Add this to {opencode_config_path()}:", "", registration_snippet(), ""]
    return [
        f"opencode was not changed: {registration.reason}.",
        "",
        f"Add this to {registration.path}:",
        "",
        registration_snippet(),
        "",
    ]


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def main() -> None:  # pragma: no cover - interactive I/O boundary
    """Entry point for `moonlighter init`."""
    home = Path(os.environ.get("MOONLIGHTER_HOME", "~/.moonlighter")).expanduser()

    print("moonlighter setup\n")
    detected = detect_browser()
    if detected:
        print(f"Found browser: {detected}")
    answers = {
        "browser_path": _ask("Browser executable path", detected or ""),
        "citizenship_country": _ask("Your citizenship country (for work authorization)"),
        "llm_backend": _ask(
            "LLM backend -- 'cli' (Claude Code), 'api', 'cursor', 'codex', or 'opencode'", "cli"
        ),
    }
    _ask_models(answers)

    try:
        config_path = run_init(home, answers)
    except FileExistsError as existing_error:
        print(f"\n{existing_error}")
        raise SystemExit(1) from existing_error

    print(f"\nWrote {config_path}")
    print(f"\nNext: add your profile at {home / 'profile.yaml'} and the companies to scan")
    print(f"at {home / 'company_list.yaml'}.\n")
    print("\n".join(next_steps(answers["llm_backend"], _maybe_register(answers["llm_backend"]))))


def _ask_models(answers: dict[str, str]) -> None:  # pragma: no cover - interactive I/O
    if answers["llm_backend"] == "codex":
        answers["llm_model"] = _ask("Codex model for answers (not a Claude id, e.g. gpt-6-luna)")
        answers["eval_model"] = _ask("Codex model for evaluations", answers["llm_model"])
    if answers["llm_backend"] == "opencode":
        answers["llm_model"] = _ask(
            "opencode model for answers, as provider/model (run `opencode models` to list them)"
        )
        answers["eval_model"] = _ask("opencode model for evaluations", answers["llm_model"])


def _maybe_register(backend: str) -> Registration | None:  # pragma: no cover - interactive I/O
    if shutil.which("opencode") is None:
        return None
    default = "y" if backend == "opencode" else "n"
    if _ask("Register moonlighter in opencode? (y/n)", default).lower() != "y":
        return None
    return register_in_opencode(opencode_config_path())
