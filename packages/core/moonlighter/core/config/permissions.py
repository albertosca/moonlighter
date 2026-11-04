"""Restricting the permissions of the sensitive files and directories under MOONLIGHTER_HOME."""

from pathlib import Path

from moonlighter.core.config.paths import moonlighter_home

_SENSITIVE_FILES = (
    "moonlighter.db",
    "profile.yaml",
    "config.yaml",
    "app.log",
    "blocklist_learned.yaml",
)
_SENSITIVE_DIRECTORIES = ("browser-session", "screenshots")


def harden_permissions() -> list[str]:
    """Set 0600/0700 on the sensitive files/subdirectories under ~/.moonlighter (S-07).

    moonlighter.db, profile.yaml and config.yaml carry full PII;
    browser-session/ holds cookies equivalent to LinkedIn credentials.
    Best-effort and never raises — a permission error becomes a warning,
    since the server must stay up even on an unusual filesystem/ACL setup.
    """
    home = moonlighter_home()
    return [
        *_restrict_existing(home, _SENSITIVE_FILES, 0o600),
        *_restrict_existing(home, _SENSITIVE_DIRECTORIES, 0o700),
    ]


def _restrict_existing(home: Path, names: tuple[str, ...], mode: int) -> list[str]:
    """Chmod each of `names` that exists under `home`; return a warning per failure."""
    warnings: list[str] = []
    for name in names:
        path = home / name
        if path.exists():
            try:
                path.chmod(mode)
            except OSError as error:
                warnings.append(f"could not restrict permissions on {path}: {error}")
    return warnings
