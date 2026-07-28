"""Interactive first-run setup: writes config.yaml and prints the MCP registration snippet.

Replaces the manual `cp config.example.yaml ~/.moonlighter/` + hand-edit flow, which was the
single largest source of setup friction for a new user.
"""

from pathlib import Path

import yaml

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
        "work_authorization": {
            "citizenship_country": answers["citizenship_country"],
            "authorized_answer": "Yes",
            "not_authorized_answer": "No",
        },
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    config_path.chmod(0o600)
    return config_path


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def main() -> None:  # pragma: no cover - interactive I/O boundary
    """Entry point for `moonlighter init`."""
    import os

    home = Path(os.environ.get("MOONLIGHTER_HOME", "~/.moonlighter")).expanduser()

    print("moonlighter setup\n")
    detected = detect_browser()
    if detected:
        print(f"Found browser: {detected}")
    answers = {
        "browser_path": _ask("Browser executable path", detected or ""),
        "citizenship_country": _ask("Your citizenship country (for work authorization)"),
        "llm_backend": _ask("LLM backend -- 'cli' (Claude Code) or 'api'", "cli"),
    }

    try:
        config_path = run_init(home, answers)
    except FileExistsError as exc:
        print(f"\n{exc}")
        raise SystemExit(1) from exc

    print(f"\nWrote {config_path}")
    print(f"\nNext: add your profile at {home / 'profile.yaml'} and the companies to scan")
    print(f"at {home / 'company_list.yaml'}.\n")
    print("Then register the MCP server:\n")
    print(
        '  claude mcp add-json --scope user moonlighter \'{"command":"uvx","args":["moonlighter"]}\''
    )
    print('\nUsing a different MCP client? Register uvx / ["moonlighter"] with its own mechanism.')
    print("\nOnce connected, ask Claude to run get_pipeline to check your setup for problems.")
