"""The Cursor backend: the `agent --print` CLI in ask mode, in a private workspace per call."""

import asyncio
import os
import shutil
from pathlib import Path
from time import perf_counter

from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.llm.cursor_projects import forget_cursor_call
from moonlighter.core.llm.isolation import kill_process_group, private_call_workdir
from moonlighter.core.metrics import record_call

# Ask mode blocks shell, web fetch, and MCP tool calls (canary, Cursor CLI
# 2026.09.28, on PR 115). It does not block reading a file outside the
# workspace — that is the permissions file below, and the file is rejected
# unless `allow` is present, even empty. Nothing here is --force / --yolo /
# --approve-mcps. There is no --no-session-persistence (a temporary HOME drops
# `agent login`), so each call gets its own workdir and that call's project
# directory is removed when the call returns.
_CURSOR_SANDBOX_ARGS: tuple[str, ...] = (
    "--print",
    "--output-format",
    "text",
    "--mode",
    "ask",
    "--sandbox",
    "enabled",
    "--trust",
)

# Exact text, not a looser dump: omitting "allow" makes the CLI exit 1 with
# "schema validation failed", and a caller that ignores that exit looks locked.
_CURSOR_PERMISSIONS_JSON = '{"permissions": {"allow": [], "deny": ["Read(/**)", "Read(~/**)"]}}\n'


def cursor_executable() -> str | None:
    """`agent` on PATH, otherwise the older `cursor-agent` binary name."""
    return shutil.which("agent") or shutil.which("cursor-agent")


def _require_agent() -> str:
    """The `agent` binary to run; a missing one says how to install it."""
    executable = cursor_executable()
    if executable is None:
        raise RuntimeError(
            "the `agent` CLI was not found on PATH (also looked for `cursor-agent`). "
            "Install the Cursor CLI and run `agent login`."
        )
    return executable


def _write_cursor_permissions(workdir: Path) -> None:
    """Deny reads outside the workspace. Ask mode alone does not."""
    cursor_directory = workdir / ".cursor"
    cursor_directory.mkdir(parents=True, exist_ok=True)
    (cursor_directory / "cli.json").write_text(_CURSOR_PERMISSIONS_JSON)


def _agent_argv(executable: str, cursor_model: str | None, workdir: Path) -> list[str]:
    """The sandbox flags, `--model` only when a Cursor model is set, then the workspace."""
    argv = [executable, *_CURSOR_SANDBOX_ARGS]
    if cursor_model:
        argv.extend(["--model", cursor_model])
    argv.extend(["--workspace", str(workdir)])
    return argv


async def _run_agent(
    argv: list[str],
    full_prompt: str,
    *,
    environment: dict[str, str],
    workdir: Path,
    timeout_seconds: float,
) -> str:
    """One `agent` process in its own process group; its stdout is the answer."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=environment,
        cwd=str(workdir),
        # Its own process group, so a timeout can take down whatever the CLI
        # started too: killing the direct process alone left a child running
        # as an orphan (2026-09-29 review of the claude CLI).
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=full_prompt.encode()), timeout=timeout_seconds
        )
    except TimeoutError:
        kill_process_group(process.pid)
        await process.wait()
        raise RuntimeError(
            f"agent CLI did not answer within {timeout_seconds} s — killed "
            "(raise llm_timeout_seconds in config.yaml if your calls are legitimately slow)"
        ) from None
    if process.returncode != 0:
        detail = stderr.decode().strip() or stdout.decode().strip()
        raise RuntimeError(f"agent CLI exited with code {process.returncode}: {detail[:300]}")
    return stdout.decode()


async def call_cursor(
    prompt: str,
    model: str,  # noqa: ARG001 - LLMCaller's signature; the Cursor CLI rejects Anthropic ids
    cache_prefix: str | None = None,
    *,
    cursor_model: str | None = None,
    timeout_seconds: float = DEFAULTS["llm_timeout_seconds"],
) -> str:
    """Call Cursor via the installed `agent` CLI.

    Same contract as `call_cli`: prompt over STDIN (never argv) and a neutral
    cwd. `model` is the Anthropic id the rest of the pipeline passes
    (`claude-sonnet-4-6`, ...); the Cursor CLI rejects those, so it is ignored.
    `cursor_model`, when set, is forwarded as `--model`. Without it the account
    default is used, and that default can change between calls. `cache_prefix`
    is concatenated before the prompt — the CLI has no cache_control.

    `--workspace` is a fresh 0700 directory under `MOONLIGHTER_HOME`, so this
    repository's MCP servers are not in scope and two calls never share a
    permissions file or a transcript directory. The user's global
    `~/.cursor/mcp.json` still is: the CLI walks project, then global, then
    nested config. In the PR 115 canary a global MCP tool was listed and the
    call was blocked in ask mode.

    `<workdir>/.cursor/cli.json` denies `Read(/**)` and `Read(~/**)` before the
    process starts. Ask mode alone still read a file outside the workspace.

    A call that has not answered within timeout_seconds is killed, process
    group included, the same way `call_cli` ends a hung `claude -p`.
    """
    full = f"{cache_prefix}\n\n{prompt}" if cache_prefix is not None else prompt
    executable = _require_agent()
    workdir = private_call_workdir("cursor-")
    _write_cursor_permissions(workdir)
    argv = _agent_argv(executable, cursor_model, workdir)
    # Same posture as `call_cli`: the agent has no use for the Anthropic key.
    environment = {key: value for key, value in os.environ.items() if key != "ANTHROPIC_API_KEY"}
    start = perf_counter()
    try:
        return await _run_agent(
            argv,
            full,
            environment=environment,
            workdir=workdir,
            timeout_seconds=timeout_seconds,
        )
    finally:
        try:
            forget_cursor_call(workdir)
        finally:
            record_call(perf_counter() - start)
