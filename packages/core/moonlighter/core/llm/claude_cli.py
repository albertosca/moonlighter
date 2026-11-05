"""The `claude` CLI backend: `claude -p` on the claude.ai session, sandboxed, prompt over stdin."""

import asyncio
import os
import shutil
from pathlib import Path
from time import perf_counter

from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.config.paths import moonlighter_home
from moonlighter.core.llm.isolation import kill_process_group
from moonlighter.core.metrics import record_call

# Sandbox posture validated empirically (canary experiment, 2026-07-09 —
# specs/2026-07-09-s2-canary-experiment-results.md): without this, the default
# `-p` reads any file on disk with no permission prompt, sees 168 account MCP
# tools, and injects the operator's global CLAUDE.md into every job evaluation.
# --bare NEVER goes here: it disables OAuth/keychain, the subscription auth
# the entire 'cli' backend exists to use.
_CLI_SANDBOX_ARGS: tuple[str, ...] = (
    "--safe-mode",
    "--no-session-persistence",
    "--tools",
    "",
    "--strict-mcp-config",
    "--mcp-config",
    '{"mcpServers":{}}',
)


def _cli_workdir() -> Path:
    """Dedicated, neutral cwd for the CLI subprocess — never the repository (S-02).

    A cwd with nothing of value for a compromised agent to explore.
    """
    workdir = moonlighter_home() / "cli-workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    workdir.chmod(0o700)
    return workdir


async def call_cli(
    prompt: str,
    model: str,  # noqa: ARG001 - LLMCaller's signature; the CLI answers with the session's model
    cache_prefix: str | None = None,
    *,
    timeout_seconds: float = DEFAULTS["llm_timeout_seconds"],
) -> str:
    """Call Claude via the installed `claude` CLI subprocess, sandboxed.

    Uses the active Claude Code session — no API key needed.
    The `model` parameter is ignored (CLI uses whichever model the session provides).
    The cache_prefix is concatenated before the prompt (the CLI doesn't expose cache_control);
    the actual caching effect only exists in the api backend.

    The prompt goes over STDIN, never argv (S-01): this removes the exposure in
    `ps` and makes argument injection structurally impossible (there's no prompt
    in argv to become a flag). The subprocess runs with an explicit set of
    lockdown flags (S-02/S-14/S-15) and in a neutral cwd outside the repository.

    A call that has not answered within timeout_seconds is killed and raises: one
    hung for 300 s on 2026-09-25 and nothing but the test harness ended it.
    """
    full = f"{cache_prefix}\n\n{prompt}" if cache_prefix is not None else prompt
    # Strip ANTHROPIC_API_KEY so the CLI uses the claude.ai session (subscription)
    # instead of the API key (which requires separate API credits).
    environment = {name: value for name, value in os.environ.items() if name != "ANTHROPIC_API_KEY"}
    executable = shutil.which("claude")
    if executable is None:
        raise RuntimeError(
            "the `claude` CLI was not found on PATH. Install it, or put it on PATH — "
            "this project uses the CLI backend (the claude.ai subscription), not an API key."
        )
    start = perf_counter()
    try:
        process = await asyncio.create_subprocess_exec(
            executable,
            *_CLI_SANDBOX_ARGS,
            "-p",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
            cwd=str(_cli_workdir()),
            # Its own process group, so a timeout can take down whatever the CLI
            # started too: killing the direct process alone left a child running
            # as an orphan (2026-09-29 review).
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=full.encode()), timeout=timeout_seconds
            )
        except TimeoutError:
            kill_process_group(process.pid)
            await process.wait()
            raise RuntimeError(
                f"claude CLI did not answer within {timeout_seconds} s — killed "
                "(raise llm_timeout_seconds in config.yaml if your calls are legitimately slow)"
            ) from None
        if process.returncode != 0:
            detail = stderr.decode().strip() or stdout.decode().strip()
            raise RuntimeError(f"claude CLI exited with code {process.returncode}: {detail[:300]}")
        return stdout.decode()
    finally:
        record_call(perf_counter() - start)
