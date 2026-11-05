import asyncio
import os
from pathlib import Path
from unittest.mock import patch

from moonlighter.core.llm.cursor import _CURSOR_SANDBOX_ARGS, call_cursor
from moonlighter.core.llm.dispatch import make_caller
from tests.core.llm.fake_processes import cursor_process


async def test_call_cursor_uses_sandbox_argv_and_stdin():
    """Prompt stays off argv (same reason as the Claude CLI: it must not show up
    in `ps`). Sandbox flags are fixed; the account model is not overridden.
    """
    mock_process = cursor_process(b"hello from cursor\n")

    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec,
        patch("moonlighter.core.llm.cursor.shutil.which", return_value="/usr/local/bin/agent"),
    ):
        result = await call_cursor("my prompt", "claude-sonnet-4-6")

    assert result == "hello from cursor\n"
    positional_arguments, keyword_arguments = mock_exec.call_args
    assert positional_arguments == (
        "/usr/local/bin/agent",
        *_CURSOR_SANDBOX_ARGS,
        "--workspace",
        keyword_arguments["cwd"],
    )
    assert "my prompt" not in positional_arguments
    assert "claude-sonnet-4-6" not in positional_arguments
    assert "--model" not in positional_arguments
    assert "--force" not in positional_arguments
    assert "--yolo" not in positional_arguments
    assert "--approve-mcps" not in positional_arguments
    assert keyword_arguments["stdin"] == asyncio.subprocess.PIPE
    assert keyword_arguments["stdout"] == asyncio.subprocess.PIPE
    assert keyword_arguments["stderr"] == asyncio.subprocess.PIPE
    assert keyword_arguments["start_new_session"] is True
    assert mock_process.communicate.call_args.kwargs["input"] == b"my prompt"


async def test_call_cursor_sandbox_args_contents():
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


async def test_call_cursor_ignores_model_param():
    mock_process = cursor_process(b"output")

    with patch(
        "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec:
        await call_cursor("prompt", "claude-opus-99")

    assert "claude-opus-99" not in mock_exec.call_args.args
    assert b"claude-opus-99" not in mock_process.communicate.call_args.kwargs["input"]


async def test_cursor_launch_invariants():
    mock_process = cursor_process(b"answer")

    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec,
        patch("moonlighter.core.llm.cursor.shutil.which", return_value="/usr/local/bin/agent"),
    ):
        await call_cursor("the prompt", "model")

    positional_arguments = mock_exec.call_args.args
    keyword_arguments = mock_exec.call_args.kwargs
    assert positional_arguments[0] == "/usr/local/bin/agent"
    assert Path(positional_arguments[0]).is_absolute()
    assert all(isinstance(argument, str) for argument in positional_arguments)
    assert "shell" not in keyword_arguments
    assert "the prompt" not in positional_arguments
    assert keyword_arguments["stdin"] is asyncio.subprocess.PIPE


async def test_call_cursor_prefers_agent_over_cursor_agent():
    mock_process = cursor_process()

    def which(name: str) -> str | None:
        return {
            "agent": "/usr/local/bin/agent",
            "cursor-agent": "/usr/local/bin/cursor-agent",
        }.get(name)

    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec,
        patch("moonlighter.core.llm.cursor.shutil.which", side_effect=which) as mock_which,
    ):
        await call_cursor("prompt", "model")

    assert mock_exec.call_args.args[0] == "/usr/local/bin/agent"
    mock_which.assert_called_once_with("agent")


async def test_call_cursor_falls_back_to_cursor_agent():
    mock_process = cursor_process()

    def which(name: str) -> str | None:
        if name == "cursor-agent":
            return "/opt/cursor-agent"
        return None

    with (
        patch(
            "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec,
        patch("moonlighter.core.llm.cursor.shutil.which", side_effect=which),
    ):
        await call_cursor("prompt", "model")

    assert mock_exec.call_args.args[0] == "/opt/cursor-agent"


async def test_call_cursor_strips_anthropic_api_key_from_the_subprocess_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    mock_process = cursor_process()

    with patch(
        "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec:
        await call_cursor("prompt", "model")

    subprocess_environment = mock_exec.call_args.kwargs["env"]
    assert "ANTHROPIC_API_KEY" not in subprocess_environment
    assert subprocess_environment["PATH"] == os.environ["PATH"]


async def test_call_cursor_forwards_cursor_model_and_ignores_a_blank_one():
    mock_process = cursor_process()

    with patch(
        "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec:
        await call_cursor("prompt", "claude-sonnet-4-6", cursor_model="gpt-5")

    positional_arguments = mock_exec.call_args.args
    assert positional_arguments[positional_arguments.index("--model") + 1] == "gpt-5"
    assert "claude-sonnet-4-6" not in positional_arguments

    with patch(
        "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec:
        caller = make_caller({"llm_backend": "cursor", "cursor_model": "  "})
        await caller("prompt", "claude-sonnet-4-6")
    assert "--model" not in mock_exec.call_args.args
