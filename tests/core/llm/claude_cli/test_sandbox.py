import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.llm.claude_cli import _CLI_SANDBOX_ARGS, _cli_workdir, call_cli


async def test_call_cli_uses_sandbox_argv_and_stdin():
    """S-01/S-02/S-14/S-15: the prompt is never in argv (kills ps disclosure and
    argument injection at once); the CLI is spawned with an explicit no-tool,
    no-MCP, no-session-persistence, no-CLAUDE.md posture."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"hello from claude\n", b""))

    with (
        patch(
            "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ) as mock_exec,
        patch("moonlighter.core.llm.claude_cli.shutil.which", return_value="/usr/local/bin/claude"),
    ):
        result = await call_cli("my prompt", "ignored-model")

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
        "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec:
        await call_cli("prompt", "model")

    keyword_arguments = mock_exec.call_args.kwargs
    assert keyword_arguments["cwd"] == str(tmp_path / "cli-workdir")


def test_cli_workdir_created_with_0700(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    workdir = _cli_workdir()
    assert workdir.exists()
    assert oct(workdir.stat().st_mode)[-3:] == "700"


def test_cli_workdir_is_idempotent(tmp_path, monkeypatch):
    """Calling it twice does not fail nor recreate the directory."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    first = _cli_workdir()
    second = _cli_workdir()
    assert first == second
    assert first.exists()


async def test_call_cli_ignores_model_param():
    """call_cli never passes model to subprocess — model is always ignored."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"output", b""))

    with patch(
        "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec:
        await call_cli("prompt", "claude-opus-99")

    call_arguments = mock_exec.call_args.args
    assert "claude-opus-99" not in call_arguments
    communicate_keyword_arguments = mock_process.communicate.call_args.kwargs
    assert b"claude-opus-99" not in communicate_keyword_arguments["input"]


async def test_cli_launch_invariants():
    """Ruff's S (flake8-bandit) rules do not analyze asyncio.create_subprocess_exec, so the
    lint gate is blind to this call. This test is the gate instead: it locks the properties
    the S rules would have enforced if they understood the API."""
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"answer", b""))
    mock_process.returncode = 0

    with (
        patch(
            "moonlighter.core.llm.claude_cli.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ) as mock_exec,
        patch("moonlighter.core.llm.claude_cli.shutil.which", return_value="/usr/local/bin/claude"),
    ):
        await call_cli("the prompt", "model")

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
