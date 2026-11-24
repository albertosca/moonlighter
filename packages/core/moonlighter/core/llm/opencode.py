"""The opencode backend: `opencode run` on any provider the person set up, one locked call each."""

import asyncio
import dataclasses
import logging
import os
import shutil
from time import perf_counter

from moonlighter.core.config.backends import is_provider_model
from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.llm.isolation import (
    CliCommand,
    private_call_workdir,
    remove_quietly,
    run_in_own_group,
)
from moonlighter.core.llm.opencode_events import RunOutput, parse_events
from moonlighter.core.llm.opencode_profile import (
    opencode_environment,
    opencode_run_argv,
    write_call_files,
)
from moonlighter.core.metrics import record_call

logger = logging.getLogger(__name__)
_SESSION_DELETE_TIMEOUT_SECONDS = 30.0
# Concurrent first calls on a fresh opencode.db: some die before the server is up
# (measured on 2.4.0). Such a run never reached the provider, so it is safe to retry.
_NOT_STARTED = "before reporting readiness"
_START_RETRIES = 2
_START_RETRY_DELAY_SECONDS = 0.5


def opencode_executable() -> str | None:
    return shutil.which("opencode")


def _require_opencode(model: str) -> str:
    """The `opencode` binary to run, once the model has the form opencode accepts."""
    if not is_provider_model(model):
        raise RuntimeError(
            "llm_backend 'opencode' needs llm_model and eval_model as provider/model "
            f"(for example 'anthropic/claude-sonnet-5-5'), got {model!r}. "
            "`opencode models` lists the ones you can run."
        )
    executable = opencode_executable()
    if executable is None:
        raise RuntimeError(
            "the `opencode` CLI was not found on PATH. Install it (https://opencode.ai) "
            "and run `opencode auth login` for your provider."
        )
    return executable


def _answer_or_raise(code: int | None, output: RunOutput, stderr: bytes) -> str:
    """The answer of a clean run; a tool call, an error event, a failed exit or silence raise."""
    if output.tools:
        raise RuntimeError(
            f"opencode called a tool ({', '.join(output.tools)}) although every tool is "
            "denied; the answer was discarded"
        )
    if output.error is not None:
        raise RuntimeError(f"opencode CLI failed: {output.error[:300]}")
    if code != 0:
        detail = stderr.decode(errors="replace").strip()
        raise RuntimeError(f"opencode CLI exited with code {code}: {detail[:300]}")
    if not output.answer.strip():
        raise RuntimeError("opencode CLI returned an empty answer")
    return output.answer


async def _delete_session(command: CliCommand) -> None:
    """Drop the call's session from opencode.db; a failure is logged and never raised."""
    try:
        code, _, stderr = await run_in_own_group(
            command, stdin=b"", timeout_seconds=_SESSION_DELETE_TIMEOUT_SECONDS
        )
    except OSError, RuntimeError:
        logger.exception("opencode session cleanup failed")
        return
    if code != 0:
        logger.warning(
            "opencode session delete exited %s: %s",
            code,
            stderr.decode(errors="replace").strip()[:300],
        )


def _never_started(output: RunOutput) -> bool:
    return output.session_id is None and _NOT_STARTED in (output.error or "")


async def _run_until_started(
    command: CliCommand, stdin: bytes, timeout_seconds: float
) -> tuple[int | None, RunOutput, bytes]:
    """One run, retried while opencode dies before its server is up."""
    for attempt in range(_START_RETRIES):
        code, stdout, stderr = await run_in_own_group(
            command, stdin=stdin, timeout_seconds=timeout_seconds
        )
        output = parse_events(stdout)
        if not _never_started(output):
            return code, output, stderr
        logger.info("opencode exited before its server was up; retrying the call")
        await asyncio.sleep(_START_RETRY_DELAY_SECONDS * (attempt + 1))
    code, stdout, stderr = await run_in_own_group(
        command, stdin=stdin, timeout_seconds=timeout_seconds
    )
    return code, parse_events(stdout), stderr


async def _run_and_clean(command: CliCommand, stdin: bytes, timeout_seconds: float) -> str:
    """Run the call, then delete the session it opened, whatever the outcome."""
    code, output, stderr = await _run_until_started(command, stdin, timeout_seconds)
    try:
        return _answer_or_raise(code, output, stderr)
    finally:
        if output.session_id is not None:
            delete = [command.argv[0], "session", "delete", "--standalone", output.session_id]
            await _delete_session(dataclasses.replace(command, argv=delete))


async def call_opencode(
    prompt: str,
    model: str,
    cache_prefix: str | None = None,
    *,
    timeout_seconds: float = DEFAULTS["llm_timeout_seconds"],
) -> str:
    """Call `model` (`provider/model`) through `opencode run`.

    Same contract as `call_codex`: prompt over STDIN, never argv; a private
    0700 workdir per call, removed when the call returns; a hung call is killed
    with its process group. The workdir holds the locked config, and the
    session is deleted afterwards so prompts do not pile up in opencode.db.
    A call that times out has its output discarded, so its session id is never
    read and that session stays.
    """
    executable = _require_opencode(model)
    # Encoded before any process or workdir exists: a prompt that cannot be encoded fails here.
    stdin_bytes = (f"{cache_prefix}\n\n{prompt}" if cache_prefix is not None else prompt).encode()
    workdir = private_call_workdir("opencode-")
    start = perf_counter()
    try:
        environment = opencode_environment(os.environ, write_call_files(workdir))
        command = CliCommand("opencode", opencode_run_argv(executable, model), environment, workdir)
        return await _run_and_clean(command, stdin_bytes, timeout_seconds)
    finally:
        try:
            remove_quietly(workdir, backend="opencode")
        finally:
            record_call(perf_counter() - start)
