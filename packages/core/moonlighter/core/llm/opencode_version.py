"""The opencode the person runs, against the one moonlighter's call isolation was measured on.

The isolation rests on opencode's env semantics (OPENCODE_CONFIG, OPENCODE_CONFIG_DIR,
OPENCODE_DISABLE_PROJECT_CONFIG), measured on 2.4. CI has no opencode binary, so an
upgrade that changed them would go unnoticed: startup says so instead.
"""

import re
import subprocess

MEASURED_VERSION = (2, 4)
_VERSION_TIMEOUT_SECONDS = 10.0
_VERSION = re.compile(r"(\d+)\.(\d+)\.\d+")


def version_drift(executable: str) -> str | None:
    """A warning when opencode is not the measured major.minor; None when it is or is unreadable."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv; the executable comes from PATH
            [executable, "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=_VERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    match = _VERSION.search(result.stdout.decode(errors="replace"))
    if result.returncode != 0 or match is None:
        return None
    if (int(match[1]), int(match[2])) == MEASURED_VERSION:
        return None
    measured = ".".join(str(part) for part in MEASURED_VERSION)
    return (
        f"opencode {match[0]} is not the {measured} release moonlighter's call isolation was "
        "verified on. Calls still run; whether your own opencode config and AGENTS.md stay "
        "out of them is unverified on this version."
    )
