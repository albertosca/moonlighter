import asyncio
import inspect
from unittest.mock import AsyncMock, patch

import pytest

from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.config.errors import ConfigError
from moonlighter.core.llm.cursor import call_cursor
from moonlighter.core.llm.dispatch import make_caller
from tests.core.llm.fake_processes import cursor_process

pytestmark = pytest.mark.usefixtures("_no_real_cursor_projects", "_fake_claude_on_path")


async def test_make_caller_cli_delegates_to_call_cli_with_the_configured_timeout():
    delegate = AsyncMock(return_value="answer")
    with patch("moonlighter.core.llm.dispatch.call_cli", delegate):
        caller = make_caller({"llm_backend": "cli", "llm_timeout_seconds": 42})
        assert await caller("prompt", "model", cache_prefix="prefix") == "answer"
    delegate.assert_awaited_once_with("prompt", "model", "prefix", timeout_seconds=42)


async def test_make_caller_cli_defaults_to_a_180_second_timeout():
    delegate = AsyncMock(return_value="answer")
    with patch("moonlighter.core.llm.dispatch.call_cli", delegate):
        await make_caller({"llm_backend": "cli"})("prompt", "model")
    assert delegate.await_args.kwargs["timeout_seconds"] == 180


def test_make_caller_api_returns_callable():
    with patch("moonlighter.core.llm.anthropic_api.anthropic"):
        caller = make_caller({"llm_backend": "api"})
    assert callable(caller)
    assert inspect.iscoroutinefunction(caller)


def test_make_caller_cursor_returns_a_cursor_caller():
    caller = make_caller({"llm_backend": "cursor"})
    assert caller is not call_cursor
    assert inspect.iscoroutinefunction(caller)


def test_make_caller_defaults_to_cli_when_backend_omitted():
    """No 'llm_backend' key → the CLI backend, matching DEFAULTS.

    Deliberate change from the previous 'api' fallback: `moonlighter init`, the
    README, and config.example.yaml all lead with the CLI, so a hand-written
    config that omits the key used to demand an API key the user never expected
    to need.
    """
    delegate = AsyncMock(return_value="answer")
    with patch("moonlighter.core.llm.dispatch.call_cli", delegate):
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


async def test_make_caller_cursor_delegates_with_the_configured_timeout():
    delegate = AsyncMock(return_value="answer")
    with patch("moonlighter.core.llm.dispatch.call_cursor", delegate):
        caller = make_caller(
            {"llm_backend": "cursor", "llm_timeout_seconds": 42, "cursor_model": "gpt-5"}
        )
        assert await caller("prompt", "model", cache_prefix="prefix") == "answer"
    delegate.assert_awaited_once_with(
        "prompt", "model", "prefix", cursor_model="gpt-5", timeout_seconds=42
    )


async def test_make_caller_cursor_defaults_to_a_180_second_timeout():
    delegate = AsyncMock(return_value="answer")
    with patch("moonlighter.core.llm.dispatch.call_cursor", delegate):
        await make_caller({"llm_backend": "cursor"})("prompt", "model")
    assert delegate.await_args.kwargs["timeout_seconds"] == 180
    assert delegate.await_args.kwargs["cursor_model"] is None


async def test_make_caller_cursor_forwards_cursor_model_and_omits_it_when_unset():
    mock_process = cursor_process()

    with patch(
        "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec:
        await make_caller({"llm_backend": "cursor", "cursor_model": "gpt-5"})(
            "prompt", "claude-haiku-4-5-20251001"
        )
    positional_arguments = mock_exec.call_args.args
    assert positional_arguments[positional_arguments.index("--model") + 1] == "gpt-5"
    assert "claude-haiku-4-5-20251001" not in positional_arguments

    with patch(
        "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec:
        await make_caller({"llm_backend": "cursor"})("prompt", "claude-sonnet-4-6")
    assert "--model" not in mock_exec.call_args.args


def test_make_caller_codex_delegates_with_the_configured_timeout():
    delegate = AsyncMock(return_value="x")
    with patch("moonlighter.core.llm.dispatch.call_codex", delegate):
        caller = make_caller({"llm_backend": "codex", "llm_timeout_seconds": 42})
        result = asyncio.run(caller("prompt", "gpt-5", "prefix"))
    assert result == "x"
    delegate.assert_awaited_once_with("prompt", "gpt-5", "prefix", timeout_seconds=42)


def test_make_caller_codex_defaults_to_the_shared_timeout():
    delegate = AsyncMock(return_value="x")
    with patch("moonlighter.core.llm.dispatch.call_codex", delegate):
        asyncio.run(make_caller({"llm_backend": "codex"})("prompt", "gpt-5"))
    assert delegate.await_args.kwargs["timeout_seconds"] == DEFAULTS["llm_timeout_seconds"]


def test_an_unknown_backend_still_lists_codex():
    with pytest.raises(ConfigError, match="cli, api, cursor, codex"):
        make_caller({"llm_backend": "nope"})
