"""The Codex backend: `codex exec` on the user's ChatGPT login, in a private workdir per call."""

import asyncio
import os
import shutil
from pathlib import Path
from time import perf_counter

from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.llm.codex_profile import codex_exec_argv
from moonlighter.core.llm.isolation import kill_process_group, private_call_workdir, remove_quietly
from moonlighter.core.llm.spend_limit import is_spend_limit
from moonlighter.core.metrics import record_call

# Never reach the child: the backend exists to bill the ChatGPT plan, so an API
# key or a base URL in the environment must not redirect the call.
_CODEX_STRIPPED_ENVIRONMENT = frozenset(
    {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"}
)
_CODEX_LOGIN_TIMEOUT_SECONDS = 20.0


def codex_executable() -> str | None:
    return shutil.which("codex")


async def _run_codex(
    argv: list[str],
    *,
    stdin: bytes,
    environment: dict[str, str],
    workdir: Path,
    timeout_seconds: float,
) -> tuple[int | None, bytes, bytes]:
    """One `codex` process in its own process group, killed whole on timeout."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=environment,
        cwd=str(workdir),
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
            f"codex CLI did not answer within {timeout_seconds} s — killed "
            "(raise llm_timeout_seconds in config.yaml if your calls are legitimately slow)"
        ) from None
    return process.returncode, stdout, stderr


def _refuse_claude_model(model: str) -> None:
    """A blank or Claude model id cannot run on Codex: refuse it before anything starts."""
    if not model.strip() or model.lower().startswith("claude"):
        raise RuntimeError(
            f"llm_backend 'codex' needs a non-Claude llm_model and eval_model in config.yaml, "
            f"got {model!r}. Set both to a model your ChatGPT plan offers."
        )


def _require_codex() -> str:
    """The `codex` binary to run; a missing one says how to install it and log in."""
    executable = codex_executable()
    if executable is None:
        raise RuntimeError(
            "the `codex` CLI was not found on PATH. Install it "
            "(`brew install --cask codex`) and run `codex login` with your ChatGPT account."
        )
    return executable


async def _require_chatgpt_login(
    executable: str, *, environment: dict[str, str], workdir: Path
) -> None:
    """Refuse the call unless `codex login status` reports a ChatGPT login."""
    code, stdout, stderr = await _run_codex(
        [executable, "login", "status"],
        stdin=b"",
        environment=environment,
        workdir=workdir,
        timeout_seconds=_CODEX_LOGIN_TIMEOUT_SECONDS,
    )
    status = (stdout + stderr).decode(errors="replace").lower()
    if code != 0 or "logged in using chatgpt" not in status:
        raise RuntimeError(
            "llm_backend 'codex' needs a ChatGPT login (an API key is not used). "
            "Run `codex login` and sign in with your ChatGPT account."
        )


def _raise_for_exit_code(code: int | None, stdout: bytes, stderr: bytes) -> None:
    """A nonzero exit raises with its detail, marked `usage limit: ` when it reads as one."""
    if code != 0:
        detail = stderr.decode(errors="replace").strip() or stdout.decode(errors="replace").strip()
        # Structured error names use underscores (`usage_limit_reached`); the
        # spend-limit markers are words.
        limited = is_spend_limit(RuntimeError(detail.replace("_", " ")))
        prefix = "usage limit: " if limited else ""
        raise RuntimeError(f"codex CLI exited with code {code}: {prefix}{detail[:300]}")


def _read_final_message(output: Path) -> str:
    """The answer `--output-last-message` wrote: a missing or blank file is an error."""
    if not output.is_file():
        raise RuntimeError("codex CLI wrote no final response")
    answer = output.read_text(encoding="utf-8")
    if not answer.strip():
        raise RuntimeError("codex CLI returned an empty final response")
    return answer


async def call_codex(
    prompt: str,
    model: str,
    cache_prefix: str | None = None,
    *,
    timeout_seconds: float = DEFAULTS["llm_timeout_seconds"],
) -> str:
    """Call a model through `codex exec`, on the user's ChatGPT login.

    Same contract as `call_cursor`: prompt over STDIN, never argv; a private
    0700 workdir per call, removed when the call returns; a hung call is killed
    with its process group. `model` is forwarded as `--model`, and a Claude id
    is refused: the pipeline's defaults are Anthropic's and Codex cannot run them.

    The call refuses to start unless `codex login status` reports a ChatGPT
    login, so a stray API key can never turn it into a billed call. The answer
    is read from `--output-last-message`, not stdout, which carries the event log.
    """
    _refuse_claude_model(model)
    executable = _require_codex()
    full = f"{cache_prefix}\n\n{prompt}" if cache_prefix is not None else prompt
    environment = {
        name: value for name, value in os.environ.items() if name not in _CODEX_STRIPPED_ENVIRONMENT
    }
    workdir = private_call_workdir("codex-")
    start = perf_counter()
    try:
        await _require_chatgpt_login(executable, environment=environment, workdir=workdir)
        output = workdir / "final-message.txt"
        code, stdout, stderr = await _run_codex(
            codex_exec_argv(executable, model, output),
            stdin=full.encode(),
            environment=environment,
            workdir=workdir,
            timeout_seconds=timeout_seconds,
        )
        _raise_for_exit_code(code, stdout, stderr)
        return _read_final_message(output)
    finally:
        try:
            remove_quietly(workdir)
        finally:
            record_call(perf_counter() - start)
