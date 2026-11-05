"""What keeps one CLI call apart: its own process group, a private workdir, and its cleanup."""

import contextlib
import os
import shutil
import signal
import tempfile
from pathlib import Path

from moonlighter.core.config.paths import moonlighter_home
from moonlighter.core.log import get_logger

logger = get_logger(__name__)


def kill_process_group(pid: int) -> None:
    # The group may have exited between the timeout and the kill.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)


def private_call_workdir(prefix: str) -> Path:
    """A private 0700 directory for one call.

    `mkdtemp` already uses that mode; the chmod repeats it so a umask change cannot widen it.
    """
    home = moonlighter_home()
    home.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix=prefix, dir=home))
    workdir.chmod(0o700)
    return workdir


def remove_quietly(path: Path) -> None:
    """Remove a tree.

    An OSError is logged and swallowed so cleanup cannot replace the call's result, including a
    usage-limit error.
    """
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except OSError:
        logger.exception("cursor cleanup failed for %s", path)
