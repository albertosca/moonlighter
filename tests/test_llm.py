import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from candidatador.llm import make_caller, _call_cli, _make_api_caller, LLMCaller


# ── make_caller factory ───────────────────────────────────────────────────────

def test_make_caller_cli_returns_call_cli():
    caller = make_caller({"llm_backend": "cli"})
    assert caller is _call_cli


def test_make_caller_api_returns_callable():
    with patch("candidatador.llm.anthropic"):
        caller = make_caller({"llm_backend": "api"})
    assert callable(caller)
    assert asyncio.iscoroutinefunction(caller)


def test_make_caller_defaults_to_api_when_key_missing():
    """No 'llm_backend' key → falls back to api caller (not _call_cli)."""
    with patch("candidatador.llm.anthropic"):
        caller = make_caller({})
    assert caller is not _call_cli
    assert callable(caller)


def test_make_caller_unknown_backend_falls_back_to_api():
    """Unknown backend string → api caller (safe default)."""
    with patch("candidatador.llm.anthropic"):
        caller = make_caller({"llm_backend": "unknown-backend"})
    assert caller is not _call_cli
    assert callable(caller)


# ── _call_cli ─────────────────────────────────────────────────────────────────

async def test_call_cli_returns_stdout():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"hello from claude\n", b""))

    with patch("candidatador.llm.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await _call_cli("my prompt", "ignored-model")

    assert result == "hello from claude\n"
    mock_exec.assert_called_once_with(
        "claude", "-p", "my prompt",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def test_call_cli_ignores_model_param():
    """_call_cli never passes model to subprocess — model is always ignored."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"output", b""))

    with patch("candidatador.llm.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        await _call_cli("prompt", "claude-opus-99")

    call_args = mock_exec.call_args[0]
    assert "claude-opus-99" not in call_args


async def test_call_cli_raises_on_nonzero_exit():
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"some error message"))

    with patch("candidatador.llm.asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(RuntimeError) as exc_info:
            await _call_cli("prompt", "model")

    assert "code 1" in str(exc_info.value)
    assert "some error message" in str(exc_info.value)


async def test_call_cli_stderr_truncated_to_300_chars():
    """Long stderr is truncated at 300 chars in the error message."""
    long_stderr = b"E" * 500
    mock_proc = MagicMock()
    mock_proc.returncode = 2
    mock_proc.communicate = AsyncMock(return_value=(b"", long_stderr))

    with patch("candidatador.llm.asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(RuntimeError) as exc_info:
            await _call_cli("p", "m")

    error_msg = str(exc_info.value)
    assert "E" * 300 in error_msg
    assert "E" * 301 not in error_msg


async def test_call_cli_empty_prompt_still_calls_subprocess():
    """Empty prompt is passed as-is to subprocess."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"response", b""))

    with patch("candidatador.llm.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await _call_cli("", "model")

    assert result == "response"
    call_args = mock_exec.call_args[0]
    assert "" in call_args


# ── _make_api_caller ──────────────────────────────────────────────────────────

async def test_make_api_caller_calls_messages_create():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="api response")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("candidatador.llm.anthropic", mock_anthropic):
        caller = _make_api_caller()
        result = await caller("my prompt", "claude-sonnet-4-6")

    assert result == "api response"
    mock_client.messages.create.assert_called_once_with(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": "my prompt"}],
    )


async def test_make_api_caller_custom_max_tokens():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("candidatador.llm.anthropic", mock_anthropic):
        caller = _make_api_caller(max_tokens=512)
        await caller("prompt", "model")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["max_tokens"] == 512


async def test_make_api_caller_forwards_model():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("candidatador.llm.anthropic", mock_anthropic):
        caller = _make_api_caller()
        await caller("prompt", "claude-opus-4-7")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-7"


async def test_make_api_caller_returns_first_content_text():
    """Returns text of first content block only."""
    mock_message = MagicMock()
    mock_message.content = [
        MagicMock(text="first block"),
        MagicMock(text="second block"),
    ]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("candidatador.llm.anthropic", mock_anthropic):
        caller = _make_api_caller()
        result = await caller("prompt", "model")

    assert result == "first block"


async def test_make_api_caller_propagates_exception():
    """Exceptions from the API are not swallowed."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("rate limit"))

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("candidatador.llm.anthropic", mock_anthropic):
        caller = _make_api_caller()
        with pytest.raises(Exception, match="rate limit"):
            await caller("prompt", "model")


def test_make_api_caller_reuses_client_across_calls():
    """_make_api_caller() creates ONE AsyncAnthropic instance, not one per call."""
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="ok")]
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("candidatador.llm.anthropic", mock_anthropic):
        caller = _make_api_caller()

    assert mock_anthropic.AsyncAnthropic.call_count == 1


# ── LLMCaller type contract ───────────────────────────────────────────────────

def test_llm_caller_type_is_exported():
    """LLMCaller is importable from candidatador.llm."""
    from candidatador.llm import LLMCaller
    assert LLMCaller is not None


async def test_cli_caller_satisfies_llm_caller_contract():
    """_call_cli satisfies (prompt: str, model: str) -> str contract."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"result", b""))

    with patch("candidatador.llm.asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await _call_cli("hello", "any-model")

    assert isinstance(result, str)


async def test_api_caller_satisfies_llm_caller_contract():
    """api caller satisfies (prompt: str, model: str) -> str contract."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="text result")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("candidatador.llm.anthropic", mock_anthropic):
        caller = _make_api_caller()
        result = await caller("hello", "any-model")

    assert isinstance(result, str)
