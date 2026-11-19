"""What keeps one CLI call apart: its own process group, a private workdir, and its cleanup."""

import asyncio
import contextlib
import logging
import os
import shutil
import signal
import tempfile
from dataclasses import dataclass
from pathlib import Path

from moonlighter.core.config.paths import moonlighter_home

logger = logging.getLogger(__name__)


def kill_process_group(pid: int) -> None:
    # The group may have exited between the timeout and the kill.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)


@dataclass(frozen=True)
class CliCommand:
    """What to start: the CLI's name for error messages, its argv, environment and cwd."""

    cli_name: str
    argv: list[str]
    environment: dict[str, str]
    workdir: Path


async def run_in_own_group(
    command: CliCommand, *, stdin: bytes, timeout_seconds: float
) -> tuple[int | None, bytes, bytes]:
    """One CLI process in its own process group, killed whole on timeout.

    Returns the exit code, stdout and stderr; what a non-zero exit means is the
    backend's call. The group matters: killing the direct process alone left a
    child the CLI started running as an orphan (2026-09-29 review).
    """
    process = await asyncio.create_subprocess_exec(
        *command.argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=command.environment,
        cwd=str(command.workdir),
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=stdin), timeout=timeout_seconds
        )
    except TimeoutError:
        kill_process_group(process.pid)
        await process.wait()
        raise RuntimeError(
            f"{command.cli_name} CLI did not answer within {timeout_seconds} s — killed "
            "(raise llm_timeout_seconds in config.yaml if your calls are legitimately slow)"
        ) from None
    return process.returncode, stdout, stderr


def stdout_or_raise(cli_name: str, result: tuple[int | None, bytes, bytes]) -> str:
    """The decoded stdout of a zero exit; otherwise a RuntimeError with the CLI's own words."""
    code, stdout, stderr = result
    if code != 0:
        detail = stderr.decode().strip() or stdout.decode().strip()
        raise RuntimeError(f"{cli_name} CLI exited with code {code}: {detail[:300]}")
    return stdout.decode()


def private_call_workdir(prefix: str) -> Path:
    """A private 0700 directory for one call.

    `mkdtemp` already uses that mode; the chmod repeats it so a umask change cannot widen it.
    """
    home = moonlighter_home()
    home.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix=prefix, dir=home))
    workdir.chmod(0o700)
    return workdir


def remove_quietly(path: Path, *, backend: str) -> None:
    """Remove a tree; `backend` names the CLI in the failure log.

    An OSError is logged and swallowed so cleanup cannot replace the call's result, including a
    usage-limit error.
    """
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except OSError:
        logger.exception("%s cleanup failed for %s", backend, path)
