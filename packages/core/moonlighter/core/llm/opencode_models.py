"""`opencode models` under the locked call's isolation: what the backend can actually run."""

import os
import subprocess
from pathlib import Path

from moonlighter.core.llm.isolation import kill_process_group, private_call_workdir, remove_quietly
from moonlighter.core.llm.opencode_profile import opencode_environment, write_call_files

_MODELS_TIMEOUT_SECONDS = 20.0


def list_opencode_models(executable: str) -> list[str] | None:
    """Every `provider/model` opencode lists, or None when the listing fails or times out.

    It runs at server startup, so it runs in its own group and is killed whole on timeout.
    """
    workdir = private_call_workdir("opencode-models-")
    try:
        stdout = _run_listing(executable, workdir)
    finally:
        remove_quietly(workdir, backend="opencode")
    if stdout is None:
        return None
    return [line.strip() for line in stdout.decode(errors="replace").splitlines() if "/" in line]


def _run_listing(executable: str, workdir: Path) -> bytes | None:
    environment = opencode_environment(os.environ, write_call_files(workdir))
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed argv; the executable comes from PATH
            [executable, "models", "--standalone"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            cwd=workdir,
            start_new_session=True,
        )
    except OSError:
        return None
    try:
        stdout, _ = process.communicate(timeout=_MODELS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        kill_process_group(process.pid)
        process.communicate()
        return None
    return stdout if process.returncode == 0 else None
