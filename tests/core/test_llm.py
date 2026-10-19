import asyncio
import inspect
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import TextBlock
from moonlighter.core.config import ConfigError
from moonlighter.core.llm import (
    LLMCaller,
    _call_cli,
    _call_cursor,
    is_spend_limit,
    make_api_caller,
    make_caller,
)


@pytest.fixture(autouse=True)
def _no_real_cursor_projects(monkeypatch):
    """Transcript cleanup must not walk the developer's ~/.cursor/projects."""
    monkeypatch.setattr(
        "moonlighter.core.llm._cursor_projects_root", lambda: Path("/no/such/cursor/projects")
    )


@pytest.fixture(autouse=True)
def _fake_claude_on_path():
    """Tests must not depend on whether `claude` happens to be installed on the
    machine running them (it never is in CI). Fix `shutil.which` to a stable
    fake path for every test in this module; tests that need a different
    resolution (found elsewhere, or absent) patch it explicitly, which
    overrides this outer patch for their duration."""
    with patch("moonlighter.core.llm.shutil.which", return_value="/usr/local/bin/claude"):
        yield


# ── make_caller factory ───────────────────────────────────────────────────────


async def test_make_caller_cli_delegates_to_call_cli_with_the_configured_timeout():
    delegate = AsyncMock(return_value="answer")
    with patch("moonlighter.core.llm._call_cli", delegate):
        caller = make_caller({"llm_backend": "cli", "llm_timeout_seconds": 42})
        assert await caller("prompt", "model", cache_prefix="prefix") == "answer"
    delegate.assert_awaited_once_with("prompt", "model", "prefix", timeout_seconds=42)


async def test_make_caller_cli_defaults_to_a_180_second_timeout():
    delegate = AsyncMock(return_value="answer")
    with patch("moonlighter.core.llm._call_cli", delegate):
        await make_caller({"llm_backend": "cli"})("prompt", "model")
    assert delegate.await_args.kwargs["timeout_seconds"] == 180


def test_make_caller_api_returns_callable():
    with patch("moonlighter.core.llm.anthropic"):
        caller = make_caller({"llm_backend": "api"})
    assert callable(caller)
    assert inspect.iscoroutinefunction(caller)


def test_make_caller_cursor_returns_a_cursor_caller():
    caller = make_caller({"llm_backend": "cursor"})
    assert caller is not _call_cursor
    assert inspect.iscoroutinefunction(caller)


def test_make_caller_defaults_to_cli_when_backend_omitted():
    """No 'llm_backend' key → the CLI backend, matching DEFAULTS.

    Deliberate change from the previous 'api' fallback: `moonlighter init`, the
    README, and config.example.yaml all lead with the CLI, so a hand-written
    config that omits the key used to demand an API key the user never expected
    to need.
    """
    delegate = AsyncMock(return_value="answer")
    with patch("moonlighter.core.llm._call_cli", delegate):
        caller = make_caller({})
    assert inspect.iscoroutinefunction(caller)
    assert caller is not None


def test_make_caller_rejects_an_unknown_backend():
    """Unknown backend string → ConfigError naming the valid values.

    It used to fall through to the api caller, so a typo like 'CLI' silently
    demanded an API key instead of using the subscription.
    """
    with pytest.raises(ConfigError, match="cli, api, cursor"):
        make_caller({"llm_backend": "CLI"})


# ── _call_cli ─────────────────────────────────────────────────────────────────


async def test_call_cli_uses_sandbox_argv_and_stdin():
    """S-01/S-02/S-14/S-15: the prompt is never in argv (kills ps disclosure and
    argument injection at once); the CLI is spawned with an explicit no-tool,
    no-MCP, no-session-persistence, no-CLAUDE.md posture."""
    from moonlighter.core.llm import _CLI_SANDBOX_ARGS

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"hello from claude\n", b""))

    with (
        patch(
            "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec,
        patch("moonlighter.core.llm.shutil.which", return_value="/usr/local/bin/claude"),
    ):
        result = await _call_cli("my prompt", "ignored-model")

    assert result == "hello from claude\n"
    positional_arguments, keyword_arguments = mock_exec.call_args
    assert positional_arguments == ("/usr/local/bin/claude", *_CLI_SANDBOX_ARGS, "-p")
    assert "my prompt" not in positional_arguments  # the prompt NEVER goes into argv
    assert keyword_arguments["stdin"] == asyncio.subprocess.PIPE
    assert keyword_arguments["stdout"] == asyncio.subprocess.PIPE
    assert keyword_arguments["stderr"] == asyncio.subprocess.PIPE
    assert "ANTHROPIC_API_KEY" not in keyword_arguments["env"]
    # communicate() receives the prompt via stdin, not via argv
    communicate_keyword_arguments = mock_process.communicate.call_args.kwargs
    assert communicate_keyword_arguments["input"] == b"my prompt"


async def test_call_cli_sandbox_args_contents():
    """Each lockdown flag is load-bearing (validated empirically in the canary) —
    locks the exact list so a future edit doesn't silently loosen it."""
    from moonlighter.core.llm import _CLI_SANDBOX_ARGS

    assert "--safe-mode" in _CLI_SANDBOX_ARGS
    assert "--no-session-persistence" in _CLI_SANDBOX_ARGS
    assert "--strict-mcp-config" in _CLI_SANDBOX_ARGS
    tools_index = _CLI_SANDBOX_ARGS.index("--tools")
    assert _CLI_SANDBOX_ARGS[tools_index + 1] == ""
    mcp_index = _CLI_SANDBOX_ARGS.index("--mcp-config")
    assert _CLI_SANDBOX_ARGS[mcp_index + 1] == '{"mcpServers":{}}'
    assert "--bare" not in _CLI_SANDBOX_ARGS  # --bare kills OAuth/keychain — forbidden


async def test_call_cli_cwd_is_neutral_workdir(tmp_path, monkeypatch):
    """cwd is never the repository — it's a dedicated directory inside MOONLIGHTER_HOME."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"ok", b""))

    with patch(
        "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec:
        await _call_cli("prompt", "model")

    keyword_arguments = mock_exec.call_args.kwargs
    assert keyword_arguments["cwd"] == str(tmp_path / "cli-workdir")


def test_cli_workdir_created_with_0700(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    from moonlighter.core.llm import _cli_workdir

    workdir = _cli_workdir()
    assert workdir.exists()
    assert oct(workdir.stat().st_mode)[-3:] == "700"


def test_cli_workdir_is_idempotent(tmp_path, monkeypatch):
    """Calling it twice does not fail nor recreate the directory."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    from moonlighter.core.llm import _cli_workdir

    first = _cli_workdir()
    second = _cli_workdir()
    assert first == second
    assert first.exists()


async def test_call_cli_ignores_model_param():
    """_call_cli never passes model to subprocess — model is always ignored."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))

    with patch(
        "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec:
        await _call_cli("prompt", "claude-opus-99")

    call_arguments = mock_exec.call_args.args
    assert "claude-opus-99" not in call_arguments
    communicate_keyword_arguments = mock_process.communicate.call_args.kwargs
    assert b"claude-opus-99" not in communicate_keyword_arguments["input"]


@pytest.mark.parametrize("group_already_gone", [False, True])
async def test_call_cli_kills_a_subprocess_that_does_not_answer_in_time(group_already_gone):
    """One `claude -p` call hung for the whole 300 s on a 1,351-character page
    (llm-tests-forge run, 2026-09-25): nothing ended it but the harness. The
    whole process group is killed (see test_llm_process_group.py for the real
    processes), and a group that exited in the meantime is not an error."""
    import asyncio
    import signal

    async def never_answers(input=None):
        await asyncio.sleep(3600)

    mock_process = MagicMock()
    mock_process.pid = 4242
    mock_process.communicate = never_answers
    mock_process.wait = AsyncMock(return_value=-9)
    killpg = MagicMock(side_effect=ProcessLookupError if group_already_gone else None)
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process),
        patch("moonlighter.core.llm.os.killpg", killpg),
        pytest.raises(RuntimeError, match=r"did not answer within 0\.05 s"),
    ):
        await _call_cli("prompt", "model", timeout_seconds=0.05)
    killpg.assert_called_once_with(4242, signal.SIGKILL)
    mock_process.wait.assert_awaited_once()


async def test_call_cli_raises_on_nonzero_exit():
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"some error message"))

    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process),
        pytest.raises(RuntimeError) as raised,
    ):
        await _call_cli("prompt", "model")

    assert "code 1" in str(raised.value)
    assert "some error message" in str(raised.value)


async def test_call_cli_stderr_truncated_to_300_chars():
    """Long stderr is truncated at 300 chars in the error message."""
    long_stderr = b"E" * 500
    mock_process = MagicMock()
    mock_process.returncode = 2
    mock_process.communicate = AsyncMock(return_value=(b"", long_stderr))

    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process),
        pytest.raises(RuntimeError) as raised,
    ):
        await _call_cli("p", "m")

    error_message = str(raised.value)
    assert "E" * 300 in error_message
    assert "E" * 301 not in error_message


async def test_call_cli_empty_prompt_still_calls_subprocess():
    """Empty prompt is passed as-is, via stdin."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"response", b""))

    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process):
        result = await _call_cli("", "model")

    assert result == "response"
    assert mock_process.communicate.call_args.kwargs["input"] == b""


async def test_cli_launch_invariants():
    """Ruff's S (flake8-bandit) rules do not analyze asyncio.create_subprocess_exec, so the
    lint gate is blind to this call. This test is the gate instead: it locks the properties
    the S rules would have enforced if they understood the API."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"answer", b""))
    mock_process.returncode = 0

    with (
        patch(
            "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec,
        patch("moonlighter.core.llm.shutil.which", return_value="/usr/local/bin/claude"),
    ):
        await _call_cli("the prompt", "model")

    positional_arguments = mock_exec.call_args.args
    keyword_arguments = mock_exec.call_args.kwargs
    # 1. Absolute path, not a bare name resolved through PATH.
    assert positional_arguments[0] == "/usr/local/bin/claude"
    assert Path(positional_arguments[0]).is_absolute()
    # 2. List form: every argument passed positionally, never one joined string.
    assert all(isinstance(argument, str) for argument in positional_arguments)
    # 3. No shell, ever.
    assert "shell" not in keyword_arguments
    # 4. The prompt is not in argv — it goes over stdin (S-01).
    assert "the prompt" not in positional_arguments
    assert keyword_arguments["stdin"] is asyncio.subprocess.PIPE


async def test_call_cli_errors_clearly_when_claude_is_not_on_path():
    with (
        patch("moonlighter.core.llm.shutil.which", return_value=None),
        pytest.raises(RuntimeError, match="claude"),
    ):
        await _call_cli("the prompt", "model")


# ── make_api_caller ──────────────────────────────────────────────────────────


async def test_make_api_caller_calls_messages_create():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="api response")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        result = await caller("my prompt", "claude-sonnet-4-6")

    assert result == "api response"
    mock_client.messages.create.assert_called_once_with(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": "my prompt"}],
    )


async def test_make_api_caller_custom_max_tokens():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller(maximum_tokens=512)
        await caller("prompt", "model")

    call_keyword_arguments = mock_client.messages.create.call_args.kwargs
    assert call_keyword_arguments["max_tokens"] == 512


async def test_make_api_caller_forwards_model():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        await caller("prompt", "claude-opus-4-7")

    call_keyword_arguments = mock_client.messages.create.call_args.kwargs
    assert call_keyword_arguments["model"] == "claude-opus-4-7"


async def test_make_api_caller_returns_first_content_text():
    """Returns text of first content block only."""
    mock_message = MagicMock()
    mock_message.content = [
        MagicMock(spec=TextBlock, text="first block"),
        MagicMock(spec=TextBlock, text="second block"),
    ]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        result = await caller("prompt", "model")

    assert result == "first block"


async def test_make_api_caller_propagates_exception():
    """Exceptions from the API are not swallowed."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("rate limit"))

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        with pytest.raises(Exception, match="rate limit"):
            await caller("prompt", "model")


def test_make_api_caller_reuses_client_across_calls():
    """make_api_caller() creates ONE AsyncAnthropic instance, not one per call."""
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic", mock_anthropic):
        make_api_caller()

    assert mock_anthropic.AsyncAnthropic.call_count == 1


# ── LLMCaller type contract ───────────────────────────────────────────────────


def test_llm_caller_type_is_exported():
    """LLMCaller is importable from moonlighter.core.llm."""
    assert LLMCaller is not None


async def test_cli_caller_satisfies_llm_caller_contract():
    """_call_cli satisfies (prompt: str, model: str) -> str contract."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"result", b""))

    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process):
        result = await _call_cli("hello", "any-model")

    assert isinstance(result, str)


async def test_api_caller_satisfies_llm_caller_contract():
    """api caller satisfies (prompt: str, model: str) -> str contract."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="text result")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        result = await caller("hello", "any-model")

    assert isinstance(result, str)


async def test_make_api_caller_raises_on_non_text_block():
    """content[0] is not a TextBlock → RuntimeError (llm.py:66)."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock()]  # no spec=TextBlock → isinstance False
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)
    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client
    with patch("moonlighter.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        with pytest.raises(RuntimeError, match="non-text block"):
            await caller("prompt", "model")


# ── cache_prefix (Task 8) ─────────────────────────────────────────────────────


async def test_cli_concatenates_cache_prefix():
    """cache_prefix is concatenated to the prompt in the cli backend."""
    captured: dict[str, bytes] = {}

    async def fake_communicate(
        *positional_arguments: object, **keyword_arguments: object
    ) -> tuple[bytes, bytes]:
        captured["input"] = keyword_arguments["input"]  # type: ignore[assignment]
        return (b"ok", b"")

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = fake_communicate

    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process):
        await _call_cli("DYN", "m", cache_prefix="STATIC")
    assert captured["input"] == b"STATIC\n\nDYN"


async def test_cli_no_cache_prefix_keeps_prompt_unchanged():
    """cache_prefix=None (default) keeps the original behavior in the cli."""
    captured: dict[str, bytes] = {}

    async def fake_communicate(
        *positional_arguments: object, **keyword_arguments: object
    ) -> tuple[bytes, bytes]:
        captured["input"] = keyword_arguments["input"]  # type: ignore[assignment]
        return (b"ok", b"")

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = fake_communicate

    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process):
        await _call_cli("PROMPT_ONLY", "m")
    assert captured["input"] == b"PROMPT_ONLY"


async def test_api_uses_cache_control_block():
    """cache_prefix becomes a content block with cache_control ephemeral in the api."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        await caller("DYN", "m", cache_prefix="STATIC")

    call_keyword_arguments = mock_client.messages.create.call_args.kwargs
    content = call_keyword_arguments["messages"][0]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "STATIC", "cache_control": {"type": "ephemeral"}}
    assert content[1] == {"type": "text", "text": "DYN"}


async def test_api_no_cache_prefix_sends_plain_string():
    """cache_prefix=None (default) keeps sending a plain string in the api."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        await caller("PROMPT_ONLY", "m")

    call_keyword_arguments = mock_client.messages.create.call_args.kwargs
    content = call_keyword_arguments["messages"][0]["content"]
    assert content == "PROMPT_ONLY"


# ── _call_cursor ──────────────────────────────────────────────────────────────


def _cursor_proc(stdout: bytes = b"ok", stderr: bytes = b"", code: int = 0) -> MagicMock:
    mock_proc = MagicMock()
    mock_proc.returncode = code
    mock_proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return mock_proc


async def test_call_cursor_uses_sandbox_argv_and_stdin():
    """Prompt stays off argv (same reason as the Claude CLI: it must not show up
    in `ps`). Sandbox flags are fixed; the account model is not overridden."""
    from moonlighter.core.llm import _CURSOR_SANDBOX_ARGS

    mock_proc = _cursor_proc(b"hello from cursor\n")

    with (
        patch(
            "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec,
        patch("moonlighter.core.llm.shutil.which", return_value="/usr/local/bin/agent"),
    ):
        result = await _call_cursor("my prompt", "claude-sonnet-4-6")

    assert result == "hello from cursor\n"
    args, kwargs = mock_exec.call_args
    assert args == (
        "/usr/local/bin/agent",
        *_CURSOR_SANDBOX_ARGS,
        "--workspace",
        kwargs["cwd"],
    )
    assert "my prompt" not in args
    assert "claude-sonnet-4-6" not in args
    assert "--model" not in args
    assert "--force" not in args
    assert "--yolo" not in args
    assert "--approve-mcps" not in args
    assert kwargs["stdin"] == asyncio.subprocess.PIPE
    assert kwargs["stdout"] == asyncio.subprocess.PIPE
    assert kwargs["stderr"] == asyncio.subprocess.PIPE
    assert kwargs["start_new_session"] is True
    assert mock_proc.communicate.call_args.kwargs["input"] == b"my prompt"


async def test_call_cursor_sandbox_args_contents():
    from moonlighter.core.llm import _CURSOR_SANDBOX_ARGS

    assert _CURSOR_SANDBOX_ARGS == (
        "--print",
        "--output-format",
        "text",
        "--mode",
        "ask",
        "--sandbox",
        "enabled",
        "--trust",
    )
    assert "--force" not in _CURSOR_SANDBOX_ARGS
    assert "--yolo" not in _CURSOR_SANDBOX_ARGS
    assert "--approve-mcps" not in _CURSOR_SANDBOX_ARGS


async def test_call_cursor_workspace_is_a_private_directory_per_call(tmp_path, monkeypatch):
    """Two calls in one home never share a workdir, and each directory is gone
    after the call. Mode is recorded while the process is starting: cleanup
    removes the directory before this function resumes."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    seen: list[tuple[Path, str]] = []

    def start(*args: object, **kwargs: object) -> MagicMock:
        workdir = Path(str(kwargs["cwd"]))
        seen.append((workdir, oct(workdir.stat().st_mode)[-3:]))
        return _cursor_proc()

    with patch(
        "moonlighter.core.llm.asyncio.create_subprocess_exec", side_effect=start
    ) as mock_exec:
        await _call_cursor("first line\nTOKEN_ONE", "claude-haiku-4-5-20251001")
        await _call_cursor("first line\nTOKEN_TWO", "claude-haiku-4-5-20251001")

    assert len(seen) == 2
    first, second = seen
    assert first[0] != second[0]
    assert first[0].parent == tmp_path
    assert second[0].parent == tmp_path
    assert first[1] == "700"
    assert second[1] == "700"
    assert not first[0].exists()
    assert not second[0].exists()
    for call in mock_exec.call_args_list:
        args = call.args
        assert args[args.index("--workspace") + 1] == call.kwargs["cwd"]


async def test_call_cursor_ignores_model_param():
    mock_proc = _cursor_proc(b"output")

    with patch(
        "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
    ) as mock_exec:
        await _call_cursor("prompt", "claude-opus-99")

    assert "claude-opus-99" not in mock_exec.call_args.args
    assert b"claude-opus-99" not in mock_proc.communicate.call_args.kwargs["input"]


async def test_call_cursor_raises_on_nonzero_exit():
    mock_proc = _cursor_proc(b"", b"some error message", code=1)

    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await _call_cursor("prompt", "model")

    assert "code 1" in str(exc_info.value)
    assert "some error message" in str(exc_info.value)


async def test_call_cursor_stderr_truncated_to_300_chars():
    mock_proc = _cursor_proc(b"", b"E" * 500, code=2)

    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await _call_cursor("p", "m")

    error_msg = str(exc_info.value)
    assert "E" * 300 in error_msg
    assert "E" * 301 not in error_msg


async def test_call_cursor_uses_stdout_when_stderr_is_empty():
    mock_proc = _cursor_proc(b"stdout detail", b"", code=1)

    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc),
        pytest.raises(RuntimeError, match="stdout detail"),
    ):
        await _call_cursor("prompt", "model")


async def test_call_cursor_empty_prompt_still_calls_subprocess():
    mock_proc = _cursor_proc(b"response")

    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await _call_cursor("", "model")

    assert result == "response"
    assert mock_proc.communicate.call_args.kwargs["input"] == b""


async def test_cursor_launch_invariants():
    mock_proc = _cursor_proc(b"answer")

    with (
        patch(
            "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec,
        patch("moonlighter.core.llm.shutil.which", return_value="/usr/local/bin/agent"),
    ):
        await _call_cursor("the prompt", "model")

    args = mock_exec.call_args.args
    kwargs = mock_exec.call_args.kwargs
    assert args[0] == "/usr/local/bin/agent"
    assert Path(args[0]).is_absolute()
    assert all(isinstance(a, str) for a in args)
    assert "shell" not in kwargs
    assert "the prompt" not in args
    assert kwargs["stdin"] is asyncio.subprocess.PIPE


async def test_call_cursor_errors_clearly_when_no_binary_is_on_path():
    with (
        patch("moonlighter.core.llm.shutil.which", return_value=None),
        pytest.raises(RuntimeError, match="agent login"),
    ):
        await _call_cursor("the prompt", "model")


async def test_call_cursor_prefers_agent_over_cursor_agent():
    mock_proc = _cursor_proc()

    def which(name: str) -> str | None:
        return {
            "agent": "/usr/local/bin/agent",
            "cursor-agent": "/usr/local/bin/cursor-agent",
        }.get(name)

    with (
        patch(
            "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec,
        patch("moonlighter.core.llm.shutil.which", side_effect=which) as mock_which,
    ):
        await _call_cursor("prompt", "model")

    assert mock_exec.call_args.args[0] == "/usr/local/bin/agent"
    mock_which.assert_called_once_with("agent")


async def test_call_cursor_falls_back_to_cursor_agent():
    mock_proc = _cursor_proc()

    def which(name: str) -> str | None:
        if name == "cursor-agent":
            return "/opt/cursor-agent"
        return None

    with (
        patch(
            "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec,
        patch("moonlighter.core.llm.shutil.which", side_effect=which),
    ):
        await _call_cursor("prompt", "model")

    assert mock_exec.call_args.args[0] == "/opt/cursor-agent"


async def test_cursor_caller_satisfies_llm_caller_contract():
    mock_proc = _cursor_proc(b"result")

    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await _call_cursor("hello", "any-model")

    assert isinstance(result, str)


async def test_cursor_concatenates_cache_prefix():
    captured: dict[str, bytes] = {}

    async def fake_communicate(*args: object, **kwargs: object) -> tuple[bytes, bytes]:
        captured["input"] = kwargs["input"]  # type: ignore[assignment]
        return (b"ok", b"")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = fake_communicate

    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc):
        await _call_cursor("DYN", "m", cache_prefix="STATIC")
    assert captured["input"] == b"STATIC\n\nDYN"


async def test_call_cursor_strips_anthropic_api_key_from_the_subprocess_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    mock_proc = _cursor_proc()

    with patch(
        "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
    ) as mock_exec:
        await _call_cursor("prompt", "model")

    env = mock_exec.call_args.kwargs["env"]
    assert "ANTHROPIC_API_KEY" not in env
    assert env["PATH"] == os.environ["PATH"]


async def test_call_cursor_writes_read_denies_before_the_subprocess(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    written: dict[str, str] = {}

    def start(*args: object, **kwargs: object) -> MagicMock:
        workdir = Path(str(kwargs["cwd"]))
        written["text"] = (workdir / ".cursor" / "cli.json").read_text()
        written["path"] = str(workdir)
        return _cursor_proc()

    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", side_effect=start):
        await _call_cursor("prompt", "model")

    assert json.loads(written["text"]) == {
        "permissions": {"allow": [], "deny": ["Read(/**)", "Read(~/**)"]},
    }
    assert '"allow": []' in written["text"]
    assert not Path(written["path"]).exists()


async def test_call_cursor_forwards_cursor_model_and_ignores_a_blank_one():
    mock_proc = _cursor_proc()

    with patch(
        "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
    ) as mock_exec:
        await _call_cursor("prompt", "claude-sonnet-4-6", cursor_model="gpt-5")

    args = mock_exec.call_args.args
    assert args[args.index("--model") + 1] == "gpt-5"
    assert "claude-sonnet-4-6" not in args

    with patch(
        "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
    ) as mock_exec:
        caller = make_caller({"llm_backend": "cursor", "cursor_model": "  "})
        await caller("prompt", "claude-sonnet-4-6")
    assert "--model" not in mock_exec.call_args.args


async def test_make_caller_cursor_delegates_with_the_configured_timeout():
    delegate = AsyncMock(return_value="answer")
    with patch("moonlighter.core.llm._call_cursor", delegate):
        caller = make_caller(
            {"llm_backend": "cursor", "llm_timeout_seconds": 42, "cursor_model": "gpt-5"}
        )
        assert await caller("prompt", "model", cache_prefix="prefix") == "answer"
    delegate.assert_awaited_once_with(
        "prompt", "model", "prefix", cursor_model="gpt-5", timeout_seconds=42
    )


async def test_make_caller_cursor_defaults_to_a_180_second_timeout():
    delegate = AsyncMock(return_value="answer")
    with patch("moonlighter.core.llm._call_cursor", delegate):
        await make_caller({"llm_backend": "cursor"})("prompt", "model")
    assert delegate.await_args.kwargs["timeout_seconds"] == 180
    assert delegate.await_args.kwargs["cursor_model"] is None


async def test_make_caller_cursor_forwards_cursor_model_and_omits_it_when_unset():
    mock_proc = _cursor_proc()

    with patch(
        "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
    ) as mock_exec:
        await make_caller({"llm_backend": "cursor", "cursor_model": "gpt-5"})(
            "prompt", "claude-haiku-4-5-20251001"
        )
    args = mock_exec.call_args.args
    assert args[args.index("--model") + 1] == "gpt-5"
    assert "claude-haiku-4-5-20251001" not in args

    with patch(
        "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
    ) as mock_exec:
        await make_caller({"llm_backend": "cursor"})("prompt", "claude-sonnet-4-6")
    assert "--model" not in mock_exec.call_args.args


def test_cursor_project_slug_matches_the_directory_cursor_creates():
    """Dots and underscores are dashes, and a doubled dash collapses. A path
    under ~/.moonlighter misses the real directory if either rule is dropped."""
    from moonlighter.core.llm import _cursor_project_slug

    assert (
        _cursor_project_slug(Path("/Users/ada/.moonlighter/cli-workdir"))
        == "Users-ada-moonlighter-cli-workdir"
    )
    assert (
        _cursor_project_slug(Path("/var/folders/x/abc_def/T/tmp.token"))
        == "var-folders-x-abc-def-T-tmp-token"
    )


def test_forget_cursor_call_removes_the_project_named_after_the_workspace(tmp_path, monkeypatch):
    """The jsonl stores a newline as the two characters \\n, so matching the
    prompt text misses every real prompt. The trust file names the workspace,
    and that is what selects the project. A stranger project stays."""
    from moonlighter.core.llm import _cursor_project_slug, _forget_cursor_call

    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr("moonlighter.core.llm._cursor_projects_root", lambda: root)
    workdir = tmp_path / "cursor-one"
    workdir.mkdir()
    prompt = "first line\nTOKEN_ONE"
    project = root / _cursor_project_slug(workdir)
    transcripts = project / "agent-transcripts"
    transcripts.mkdir(parents=True)
    (transcripts / "a.jsonl").write_text(prompt.replace("\n", "\\n"))
    (project / ".workspace-trusted").write_text('{"workspacePath": "' + str(workdir) + '"}')
    stranger = root / "other-editor-session" / "agent-transcripts"
    stranger.mkdir(parents=True)
    (stranger / "c.jsonl").write_text("brand new but unrelated")

    _forget_cursor_call(workdir)

    assert not project.exists()
    assert not workdir.exists()
    assert (stranger / "c.jsonl").read_text() == "brand new but unrelated"


def test_forget_cursor_call_finds_a_project_whose_name_is_not_the_slug(tmp_path, monkeypatch):
    from moonlighter.core.llm import _forget_cursor_call

    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr("moonlighter.core.llm._cursor_projects_root", lambda: root)
    workdir = tmp_path / "cursor-two"
    workdir.mkdir()
    project = root / "whatever-the-cli-picked"
    (project / "agent-transcripts").mkdir(parents=True)
    (project / "agent-transcripts" / "a.jsonl").write_text("first line\\nTOKEN_TWO")
    (project / ".workspace-trusted").write_text(str(workdir.resolve()))
    untouched = root / "no-trust-file"
    untouched.mkdir()
    decoy = root / "other-workspace"
    decoy.mkdir()
    (decoy / ".workspace-trusted").write_text("/somewhere/else")
    (root / "not-a-project").write_text("ignored")

    _forget_cursor_call(workdir)

    assert not project.exists()
    assert untouched.is_dir()
    assert (decoy / ".workspace-trusted").read_text() == "/somewhere/else"
    assert not workdir.exists()


def test_forget_cursor_call_skips_an_unreadable_trust_file(tmp_path, monkeypatch):
    from moonlighter.core.llm import _cursor_projects_for

    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr("moonlighter.core.llm._cursor_projects_root", lambda: root)
    workdir = tmp_path / "cursor-three"
    workdir.mkdir()
    unreadable = root / "unreadable"
    unreadable.mkdir()
    (unreadable / ".workspace-trusted").write_text(str(workdir))
    readable = root / "readable"
    readable.mkdir()
    (readable / ".workspace-trusted").write_text(str(workdir))
    original = Path.read_text

    def read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.parent == unreadable:
            raise OSError("gone")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)

    assert _cursor_projects_for(workdir) == [readable]


def test_forget_cursor_call_gives_up_when_listing_projects_fails(tmp_path, monkeypatch):
    from moonlighter.core.llm import _cursor_projects_for, _forget_cursor_call

    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr("moonlighter.core.llm._cursor_projects_root", lambda: root)
    workdir = tmp_path / "cursor-four"
    workdir.mkdir()

    def iterdir(self: Path):
        if self == root:
            raise OSError("denied")
        return []

    monkeypatch.setattr(Path, "iterdir", iterdir)

    assert _cursor_projects_for(workdir) == []
    _forget_cursor_call(workdir)
    assert not workdir.exists()


def test_forget_cursor_call_is_a_no_op_when_nothing_is_there(tmp_path, monkeypatch):
    from moonlighter.core.llm import _forget_cursor_call

    missing = tmp_path / "absent"
    monkeypatch.setattr("moonlighter.core.llm._cursor_projects_root", lambda: missing)
    _forget_cursor_call(tmp_path / "workdir")


@pytest.mark.parametrize("group_already_gone", [False, True])
async def test_call_cursor_kills_a_subprocess_that_does_not_answer_in_time(group_already_gone):
    """Same rule as the claude CLI: a hung agent is killed with its process
    group, and a group that already exited is not an error."""
    import signal

    async def never_answers(input=None):
        await asyncio.sleep(3600)

    mock_process = MagicMock()
    mock_process.pid = 4242
    mock_process.communicate = never_answers
    mock_process.wait = AsyncMock(return_value=-9)
    killpg = MagicMock(side_effect=ProcessLookupError if group_already_gone else None)
    with (
        patch(
            "moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec,
        patch("moonlighter.core.llm.os.killpg", killpg),
        pytest.raises(RuntimeError, match=r"agent CLI did not answer within 0\.05 s"),
    ):
        await _call_cursor("prompt", "model", timeout_seconds=0.05)
    killpg.assert_called_once_with(4242, signal.SIGKILL)
    mock_process.wait.assert_awaited_once()
    assert mock_exec.call_args.kwargs["start_new_session"] is True


async def test_cursor_cleanup_failure_does_not_replace_the_result(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    mock_process = _cursor_proc(b"the answer")
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process),
        patch("moonlighter.core.llm.shutil.rmtree", side_effect=OSError("busy")),
        caplog.at_level("ERROR"),
    ):
        result = await _call_cursor("prompt", "model")
    assert result == "the answer"
    assert "cursor cleanup failed" in caplog.text


async def test_cursor_cleanup_failure_does_not_hide_a_usage_limit(tmp_path, monkeypatch):
    mock_process = _cursor_proc()
    mock_process.communicate = AsyncMock(side_effect=RuntimeError("usage limit reached"))
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_process),
        patch("moonlighter.core.llm.shutil.rmtree", side_effect=OSError("busy")),
        pytest.raises(RuntimeError, match="usage limit"),
    ):
        await _call_cursor("prompt", "model")


async def test_parallel_cursor_calls_keep_their_own_permissions_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    seen: list[Path] = []

    async def start(*args: object, **kwargs: object) -> MagicMock:
        workdir = Path(str(kwargs["cwd"]))
        seen.append(workdir)
        permissions = (workdir / ".cursor" / "cli.json").read_text()
        process = _cursor_proc()

        async def communicate(input: object = None) -> tuple[bytes, bytes]:
            await asyncio.sleep(0.05)
            assert (workdir / ".cursor" / "cli.json").read_text() == permissions
            return b"ok", b""

        process.communicate = communicate
        return process

    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", side_effect=start):
        await asyncio.gather(
            _call_cursor("first line\nTOKEN_ONE", "model"),
            _call_cursor("first line\nTOKEN_TWO", "model"),
        )

    assert len(seen) == 2
    assert seen[0] != seen[1]
    assert not seen[0].exists()
    assert not seen[1].exists()


def test_cursor_projects_root_is_the_home_projects_dir(monkeypatch):
    monkeypatch.undo()
    from moonlighter.core.llm import _cursor_projects_root

    assert _cursor_projects_root() == Path.home() / ".cursor" / "projects"


async def test_cursor_no_cache_prefix_keeps_prompt_unchanged():
    captured: dict[str, bytes] = {}

    async def fake_communicate(*args: object, **kwargs: object) -> tuple[bytes, bytes]:
        captured["input"] = kwargs["input"]  # type: ignore[assignment]
        return (b"ok", b"")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = fake_communicate

    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc):
        await _call_cursor("PROMPT_ONLY", "m")
    assert captured["input"] == b"PROMPT_ONLY"


# ── is_spend_limit ────────────────────────────────────────────────────────────


class _CustomAPIError(Exception):
    """Stand-in for a real SDK exception type (e.g. anthropic.RateLimitError)."""


IS_SPEND_LIMIT_CASES = [
    # (exception, expected, case id)
    (Exception("spend limit reached"), True, "spend-limit-plain"),
    (Exception("Spend Limit Reached"), True, "spend-limit-mixed-case"),
    (Exception("SPEND LIMIT EXCEEDED FOR ORG"), True, "spend-limit-upper"),
    (Exception("your session limit has been hit"), True, "session-limit"),
    (Exception("quota exceeded for this project"), True, "quota"),
    (Exception("rate limit exceeded, please retry"), True, "rate-limit"),
    (Exception("too many requests in a short period"), True, "too-many-requests"),
    (Exception("the API is currently overloaded"), True, "overloaded"),
    (Exception("HTTP 429 returned by upstream"), True, "429-in-http-status"),
    (Exception("usage limit for this key was reached"), True, "usage-limit"),
    # Marker embedded deep inside a longer, unrelated-looking message.
    (
        Exception("Traceback (most recent call last): anthropic.RateLimitError: rate limit"),
        True,
        "marker-embedded-in-traceback",
    ),
    # A real SDK-shaped exception type, not just builtin Exception.
    (_CustomAPIError("429 Too Many Requests"), True, "custom-exception-type"),
    # Wrapped exception: __str__ of the outer exception must still surface the marker.
    (
        RuntimeError(f"llm call failed: {ValueError('quota exceeded')}"),
        True,
        "wrapped-exception-str-propagates-marker",
    ),
    # ── should NOT be classified as spend-limit ──
    (Exception("connection refused"), False, "unrelated-connection-error"),
    (Exception("invalid api key"), False, "unrelated-auth-error"),
    (Exception("file not found: /tmp/x.json"), False, "unrelated-file-error"),
    (Exception(""), False, "empty-message"),
    (Exception("timeout while waiting for response"), False, "timeout-not-a-marker"),
    (ValueError("malformed JSON in response body"), False, "unrelated-value-error"),
    (KeyError("missing_field"), False, "unrelated-key-error"),
    # Partial/incomplete phrases: only a fragment of a two-word marker present.
    (Exception("spend more time reviewing"), False, "partial-phrase-spend-without-limit"),
    (Exception("limit your expectations"), False, "partial-phrase-limit-without-spend"),
    (Exception("rate this job highly"), False, "partial-phrase-rate-without-limit"),
    # Regression: bare substring matching let "quota" match inside "quotation"
    # and "429" match inside "4290" — a false positive here ABORTS THE WHOLE
    # SCAN, so these must stay False under word-boundary matching.
    (Exception("malformed quotation marks in JSON"), False, "quota-substring-of-quotation"),
    (Exception("connection refused on port 4290"), False, "429-substring-of-4290"),
    (Exception("error 14293 occurred"), False, "429-substring-of-14293"),
    # Real spend-limit phrasings that must keep matching after the word-boundary fix.
    (Exception("quota exceeded"), True, "quota-exceeded-word-boundary"),
    (Exception("429 Too Many Requests"), True, "429-leading-word-boundary"),
    (Exception("error 429"), True, "429-trailing-word-boundary"),
]


@pytest.mark.parametrize(
    "error,expected",
    [(error, expected) for error, expected, _ in IS_SPEND_LIMIT_CASES],
    ids=[case_id for _, _, case_id in IS_SPEND_LIMIT_CASES],
)
def test_is_spend_limit_table(error: Exception, expected: bool) -> None:
    assert is_spend_limit(error) is expected
