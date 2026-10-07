import asyncio
import contextlib
import os
import re
import shutil
import signal
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

import anthropic
from anthropic.types import TextBlock
from moonlighter.core.config import DEFAULTS, llm_backend, moonlighter_home
from moonlighter.core.metrics import record_call


class LLMCaller(Protocol):
    """LLM caller protocol: accepts prompt, model, and optional cache_prefix."""

    async def __call__(self, prompt: str, model: str, cache_prefix: str | None = None) -> str: ...


# Signals that the LLM exhausted its quota/spend limit — worth aborting the
# scan and retrying later, instead of treating it as a per-job error.
SPEND_LIMIT_MARKERS = (
    "spend limit",
    "session limit",
    "quota",
    "rate limit",
    "too many requests",
    "overloaded",
    "429",
    "usage limit",
)

# Word-boundary match so markers only fire on real tokens: bare substring
# matching let "quota" match inside "quotation" and "429" match inside "4290",
# false-positive-aborting the whole scan on unrelated JSON/network errors.
_SPEND_LIMIT_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(marker) for marker in SPEND_LIMIT_MARKERS) + r")\b"
)


def is_spend_limit(error: Exception) -> bool:
    """True if the exception indicates the LLM's quota/spend limit was exhausted."""
    message = str(error).lower()
    return bool(_SPEND_LIMIT_PATTERN.search(message))


def make_caller(config: dict[str, Any]) -> LLMCaller:
    """Return the appropriate LLM caller based on config['llm_backend'].

    llm_backend: "cli"     → uses the `claude -p` CLI (no API key required)
    llm_backend: "api"     → uses the Anthropic Python SDK (requires ANTHROPIC_API_KEY)
    llm_backend: "cursor"  → uses the Cursor `agent --print` CLI (`agent login`).
                             Optional config key `cursor_model` is forwarded as
                             `--model`; `llm_model` / `eval_model` are not.
    Default: "cli". Anything else raises ConfigError rather than silently
    selecting a backend the user did not ask for.
    """
    backend = llm_backend(config)
    if backend == "cli":
        timeout_seconds = config.get("llm_timeout_seconds", DEFAULTS["llm_timeout_seconds"])

        async def _call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
            return await _call_cli(prompt, model, cache_prefix, timeout_seconds=timeout_seconds)

        return _call
    if backend == "cursor":
        chosen = str(config.get("cursor_model") or "").strip()
        return _cursor_caller(chosen or None)
    return make_api_caller()


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
    """Dedicated, neutral cwd for the CLI subprocess — never the repository
    (S-02): a cwd with nothing of value for a compromised agent to explore."""
    workdir = moonlighter_home() / "cli-workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    workdir.chmod(0o700)
    return workdir


async def _call_cli(
    prompt: str,
    model: str,
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
    exe = shutil.which("claude")
    if exe is None:
        raise RuntimeError(
            "the `claude` CLI was not found on PATH. Install it, or put it on PATH — "
            "this project uses the CLI backend (the claude.ai subscription), not an API key."
        )
    start = perf_counter()
    try:
        process = await asyncio.create_subprocess_exec(
            exe,
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
            _kill_process_group(process.pid)
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


# Ask mode blocks shell, web fetch, and MCP tool calls (canary, Cursor CLI
# 2026.09.28, on PR 115). It does not block reading a file outside the
# workspace — that is the permissions file below, and the file is rejected
# unless `allow` is present, even empty. Nothing here is --force / --yolo /
# --approve-mcps. There is no --no-session-persistence (a temporary HOME drops
# `agent login`), so transcripts are removed after the call instead.
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


def _cursor_caller(cursor_model: str | None) -> LLMCaller:
    """Bind the optional Cursor model. The `model` argument stays the Anthropic id."""

    async def _call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return await _call_cursor(prompt, model, cache_prefix, cursor_model=cursor_model)

    return _call


def _write_cursor_permissions(workdir: Path) -> None:
    """Deny reads outside the workspace. Ask mode alone does not."""
    cursor_dir = workdir / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    (cursor_dir / "cli.json").write_text(_CURSOR_PERMISSIONS_JSON)


def _cursor_projects_root() -> Path:
    return Path.home() / ".cursor" / "projects"


def _snapshot_cursor_projects() -> dict[Path, tuple[int, int]]:
    """mtime and size of every file under the Cursor projects dir, if it exists."""
    root = _cursor_projects_root()
    if not root.is_dir():
        return {}
    snap: dict[Path, tuple[int, int]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        snap[path] = (stat.st_mtime_ns, stat.st_size)
    return snap


def _forget_cursor_transcripts(
    before: dict[Path, tuple[int, int]], workdir: Path, prompt: str
) -> None:
    """Remove agent transcripts this call just wrote.

    The jsonl quotes the prompt, not the workspace path. A sibling written in
    the same project dir (`.workspace-trusted`) quotes the workspace path. Either
    mark, on a file that appeared or changed during the call, selects that
    project. Only its `agent-transcripts` directory is removed, so a concurrent
    Cursor session and an unchanged history are left alone. The slug is whatever
    directory the CLI created — it is not recomputed here.
    """
    root = _cursor_projects_root()
    if not root.is_dir():
        return
    marks = {str(workdir), str(workdir.resolve())}
    if prompt:
        marks.add(prompt)
    projects: set[Path] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        if before.get(path) == (stat.st_mtime_ns, stat.st_size):
            continue
        text = path.read_text(errors="replace")
        if not any(mark in text for mark in marks):
            continue
        projects.add(root / path.relative_to(root).parts[0])
    for project in projects:
        transcripts = project / "agent-transcripts"
        if transcripts.is_dir():
            shutil.rmtree(transcripts)


async def _call_cursor(
    prompt: str,
    model: str,
    cache_prefix: str | None = None,
    cursor_model: str | None = None,
) -> str:
    """Call Cursor via the installed `agent` CLI.

    Same contract as `_call_cli`: prompt over STDIN (never argv) and a neutral
    cwd. `model` is the Anthropic id the rest of the pipeline passes
    (`claude-sonnet-4-6`, ...); the Cursor CLI rejects those, so it is ignored.
    `cursor_model`, when set, is forwarded as `--model`. Without it the account
    default is used, and that default can change between calls. `cache_prefix`
    is concatenated before the prompt — the CLI has no cache_control.

    `--workspace` is the same 0700 directory `_call_cli` uses, so this
    repository's MCP servers are not in scope. The user's global
    `~/.cursor/mcp.json` still is: the CLI walks project, then global, then
    nested config. In the PR 115 canary a global MCP tool was listed and the
    call was blocked in ask mode.

    `<workdir>/.cursor/cli.json` denies `Read(/**)` and `Read(~/**)` before the
    process starts. Ask mode alone still read a file outside the workspace.
    """
    full = f"{cache_prefix}\n\n{prompt}" if cache_prefix is not None else prompt
    exe = cursor_executable()
    if exe is None:
        raise RuntimeError(
            "the `agent` CLI was not found on PATH (also looked for `cursor-agent`). "
            "Install the Cursor CLI and run `agent login`."
        )
    workdir = _cli_workdir()
    _write_cursor_permissions(workdir)
    argv = [exe, *_CURSOR_SANDBOX_ARGS]
    if cursor_model:
        argv.extend(["--model", cursor_model])
    argv.extend(["--workspace", str(workdir)])
    # Same posture as `_call_cli`: the agent has no use for the Anthropic key.
    env = {key: value for key, value in os.environ.items() if key != "ANTHROPIC_API_KEY"}
    before = _snapshot_cursor_projects()
    start = perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(workdir),
        )
        stdout, stderr = await proc.communicate(input=full.encode())
        if proc.returncode != 0:
            detail = stderr.decode().strip() or stdout.decode().strip()
            raise RuntimeError(f"agent CLI exited with code {proc.returncode}: {detail[:300]}")
        return stdout.decode()
    finally:
        try:
            _forget_cursor_transcripts(before, workdir, full)
        finally:
            record_call(perf_counter() - start)


def _kill_process_group(pid: int) -> None:
    # The group may have exited between the timeout and the kill.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)


def make_api_caller(maximum_tokens: int = 2048) -> LLMCaller:
    """Return an async caller that uses the Anthropic Python SDK.

    Requires ANTHROPIC_API_KEY in the environment.
    """
    client = anthropic.AsyncAnthropic()

    async def _call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        # When cache_prefix is provided, sends two blocks: the static prefix
        # with ephemeral cache_control (marked for caching on Anthropic's side)
        # followed by the dynamic prompt. Without a prefix, sends a plain string (backcompat).
        if cache_prefix is not None:
            content: Any = [
                {"type": "text", "text": cache_prefix, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": prompt},
            ]
        else:
            content = prompt
        start = perf_counter()
        input_tokens = output_tokens = 0
        try:
            message = await client.messages.create(
                model=model,
                max_tokens=maximum_tokens,
                messages=[{"role": "user", "content": content}],
            )
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            block = message.content[0]
            if not isinstance(block, TextBlock):
                raise RuntimeError("unexpected model response (non-text block)")
            return block.text
        finally:
            record_call(
                perf_counter() - start, input_tokens=input_tokens, output_tokens=output_tokens
            )

    return _call
