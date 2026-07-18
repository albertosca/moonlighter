import asyncio
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import TextBlock
from gauntler.core.llm import LLMCaller, _call_cli, is_spend_limit, make_api_caller, make_caller


@pytest.fixture(autouse=True)
def _fake_claude_on_path():
    """Tests must not depend on whether `claude` happens to be installed on the
    machine running them (it never is in CI). Fix `shutil.which` to a stable
    fake path for every test in this module; tests that need a different
    resolution (found elsewhere, or absent) patch it explicitly, which
    overrides this outer patch for their duration."""
    with patch("gauntler.core.llm.shutil.which", return_value="/usr/local/bin/claude"):
        yield


# ── make_caller factory ───────────────────────────────────────────────────────


def test_make_caller_cli_returns_call_cli():
    caller = make_caller({"llm_backend": "cli"})
    assert caller is _call_cli


def test_make_caller_api_returns_callable():
    with patch("gauntler.core.llm.anthropic"):
        caller = make_caller({"llm_backend": "api"})
    assert callable(caller)
    assert inspect.iscoroutinefunction(caller)


def test_make_caller_defaults_to_api_when_key_missing():
    """No 'llm_backend' key → falls back to api caller (not _call_cli)."""
    with patch("gauntler.core.llm.anthropic"):
        caller = make_caller({})
    assert caller is not _call_cli
    assert callable(caller)


def test_make_caller_unknown_backend_falls_back_to_api():
    """Unknown backend string → api caller (safe default)."""
    with patch("gauntler.core.llm.anthropic"):
        caller = make_caller({"llm_backend": "unknown-backend"})
    assert caller is not _call_cli
    assert callable(caller)


# ── _call_cli ─────────────────────────────────────────────────────────────────


async def test_call_cli_uses_sandbox_argv_and_stdin():
    """S-01/S-02/S-14/S-15: the prompt is never in argv (kills ps disclosure and
    argument injection at once); the CLI is spawned with an explicit no-tool,
    no-MCP, no-session-persistence, no-CLAUDE.md posture."""
    from gauntler.core.llm import _CLI_SANDBOX_ARGS

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"hello from claude\n", b""))

    with (
        patch(
            "gauntler.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec,
        patch("gauntler.core.llm.shutil.which", return_value="/usr/local/bin/claude"),
    ):
        result = await _call_cli("my prompt", "ignored-model")

    assert result == "hello from claude\n"
    args, kwargs = mock_exec.call_args
    assert args == ("/usr/local/bin/claude", *_CLI_SANDBOX_ARGS, "-p")
    assert "my prompt" not in args  # o prompt NUNCA vai em argv
    assert kwargs["stdin"] == asyncio.subprocess.PIPE
    assert kwargs["stdout"] == asyncio.subprocess.PIPE
    assert kwargs["stderr"] == asyncio.subprocess.PIPE
    assert "ANTHROPIC_API_KEY" not in kwargs["env"]
    # communicate() recebe o prompt via stdin, não via argv
    communicate_kwargs = mock_proc.communicate.call_args.kwargs
    assert communicate_kwargs["input"] == b"my prompt"


async def test_call_cli_sandbox_args_contents():
    """Cada flag do lockdown é load-bearing (validado empiricamente no canário) —
    trava a lista exata para que uma edição futura não a afrouxe silenciosamente."""
    from gauntler.core.llm import _CLI_SANDBOX_ARGS

    assert "--safe-mode" in _CLI_SANDBOX_ARGS
    assert "--no-session-persistence" in _CLI_SANDBOX_ARGS
    assert "--strict-mcp-config" in _CLI_SANDBOX_ARGS
    tools_idx = _CLI_SANDBOX_ARGS.index("--tools")
    assert _CLI_SANDBOX_ARGS[tools_idx + 1] == ""
    mcp_idx = _CLI_SANDBOX_ARGS.index("--mcp-config")
    assert _CLI_SANDBOX_ARGS[mcp_idx + 1] == '{"mcpServers":{}}'
    assert "--bare" not in _CLI_SANDBOX_ARGS  # --bare mata OAuth/keychain — proibido


async def test_call_cli_cwd_is_neutral_workdir(tmp_path, monkeypatch):
    """cwd nunca é o repositório — é um diretório dedicado dentro de GAUNTLER_HOME."""
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))

    with patch(
        "gauntler.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
    ) as mock_exec:
        await _call_cli("prompt", "model")

    kwargs = mock_exec.call_args.kwargs
    assert kwargs["cwd"] == str(tmp_path / "cli-workdir")


def test_cli_workdir_created_with_0700(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    from gauntler.core.llm import _cli_workdir

    workdir = _cli_workdir()
    assert workdir.exists()
    assert oct(workdir.stat().st_mode)[-3:] == "700"


def test_cli_workdir_is_idempotent(tmp_path, monkeypatch):
    """Chamar duas vezes não falha nem recria o diretório."""
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    from gauntler.core.llm import _cli_workdir

    first = _cli_workdir()
    second = _cli_workdir()
    assert first == second
    assert first.exists()


async def test_call_cli_ignores_model_param():
    """_call_cli never passes model to subprocess — model is always ignored."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"output", b""))

    with patch(
        "gauntler.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
    ) as mock_exec:
        await _call_cli("prompt", "claude-opus-99")

    call_args = mock_exec.call_args.args
    assert "claude-opus-99" not in call_args
    communicate_kwargs = mock_proc.communicate.call_args.kwargs
    assert b"claude-opus-99" not in communicate_kwargs["input"]


async def test_call_cli_raises_on_nonzero_exit():
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"some error message"))

    with (
        patch("gauntler.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await _call_cli("prompt", "model")

    assert "code 1" in str(exc_info.value)
    assert "some error message" in str(exc_info.value)


async def test_call_cli_stderr_truncated_to_300_chars():
    """Long stderr is truncated at 300 chars in the error message."""
    long_stderr = b"E" * 500
    mock_proc = MagicMock()
    mock_proc.returncode = 2
    mock_proc.communicate = AsyncMock(return_value=(b"", long_stderr))

    with (
        patch("gauntler.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await _call_cli("p", "m")

    error_msg = str(exc_info.value)
    assert "E" * 300 in error_msg
    assert "E" * 301 not in error_msg


async def test_call_cli_empty_prompt_still_calls_subprocess():
    """Empty prompt is passed as-is, via stdin."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"response", b""))

    with patch("gauntler.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await _call_cli("", "model")

    assert result == "response"
    assert mock_proc.communicate.call_args.kwargs["input"] == b""


async def test_cli_launch_invariants():
    """Ruff's S (flake8-bandit) rules do not analyze asyncio.create_subprocess_exec, so the
    lint gate is blind to this call. This test is the gate instead: it locks the properties
    the S rules would have enforced if they understood the API."""
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"answer", b""))
    mock_proc.returncode = 0

    with (
        patch(
            "gauntler.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec,
        patch("gauntler.core.llm.shutil.which", return_value="/usr/local/bin/claude"),
    ):
        await _call_cli("the prompt", "model")

    args = mock_exec.call_args.args
    kwargs = mock_exec.call_args.kwargs
    # 1. Absolute path, not a bare name resolved through PATH.
    assert args[0] == "/usr/local/bin/claude"
    assert Path(args[0]).is_absolute()
    # 2. List form: every argument passed positionally, never one joined string.
    assert all(isinstance(a, str) for a in args)
    # 3. No shell, ever.
    assert "shell" not in kwargs
    # 4. The prompt is not in argv — it goes over stdin (S-01).
    assert "the prompt" not in args
    assert kwargs["stdin"] is asyncio.subprocess.PIPE


async def test_call_cli_errors_clearly_when_claude_is_not_on_path():
    with (
        patch("gauntler.core.llm.shutil.which", return_value=None),
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

    with patch("gauntler.core.llm.anthropic", mock_anthropic):
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

    with patch("gauntler.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller(max_tokens=512)
        await caller("prompt", "model")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["max_tokens"] == 512


async def test_make_api_caller_forwards_model():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("gauntler.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        await caller("prompt", "claude-opus-4-7")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-7"


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

    with patch("gauntler.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        result = await caller("prompt", "model")

    assert result == "first block"


async def test_make_api_caller_propagates_exception():
    """Exceptions from the API are not swallowed."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("rate limit"))

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("gauntler.core.llm.anthropic", mock_anthropic):
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

    with patch("gauntler.core.llm.anthropic", mock_anthropic):
        make_api_caller()

    assert mock_anthropic.AsyncAnthropic.call_count == 1


# ── LLMCaller type contract ───────────────────────────────────────────────────


def test_llm_caller_type_is_exported():
    """LLMCaller is importable from gauntler.core.llm."""
    assert LLMCaller is not None


async def test_cli_caller_satisfies_llm_caller_contract():
    """_call_cli satisfies (prompt: str, model: str) -> str contract."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"result", b""))

    with patch("gauntler.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc):
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

    with patch("gauntler.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        result = await caller("hello", "any-model")

    assert isinstance(result, str)


async def test_make_api_caller_raises_on_non_text_block():
    """content[0] não é TextBlock → RuntimeError (llm.py:66)."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock()]  # sem spec=TextBlock → isinstance False
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)
    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client
    with patch("gauntler.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        with pytest.raises(RuntimeError, match="bloco não-texto"):
            await caller("prompt", "model")


# ── cache_prefix (Task 8) ─────────────────────────────────────────────────────


async def test_cli_concatenates_cache_prefix():
    """cache_prefix é concatenado ao prompt no backend cli."""
    captured: dict[str, bytes] = {}

    async def fake_communicate(*args: object, **kwargs: object) -> tuple[bytes, bytes]:
        captured["input"] = kwargs["input"]  # type: ignore[assignment]
        return (b"ok", b"")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = fake_communicate

    with patch("gauntler.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc):
        await _call_cli("DYN", "m", cache_prefix="STATIC")
    assert captured["input"] == b"STATIC\n\nDYN"


async def test_cli_no_cache_prefix_keeps_prompt_unchanged():
    """cache_prefix=None (default) mantém o comportamento original no cli."""
    captured: dict[str, bytes] = {}

    async def fake_communicate(*args: object, **kwargs: object) -> tuple[bytes, bytes]:
        captured["input"] = kwargs["input"]  # type: ignore[assignment]
        return (b"ok", b"")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = fake_communicate

    with patch("gauntler.core.llm.asyncio.create_subprocess_exec", return_value=mock_proc):
        await _call_cli("PROMPT_ONLY", "m")
    assert captured["input"] == b"PROMPT_ONLY"


async def test_api_uses_cache_control_block():
    """cache_prefix vira um content block com cache_control ephemeral no api."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("gauntler.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        await caller("DYN", "m", cache_prefix="STATIC")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    content = call_kwargs["messages"][0]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "STATIC", "cache_control": {"type": "ephemeral"}}
    assert content[1] == {"type": "text", "text": "DYN"}


async def test_api_no_cache_prefix_sends_plain_string():
    """cache_prefix=None (default) mantém envio de string simples no api."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("gauntler.core.llm.anthropic", mock_anthropic):
        caller = make_api_caller()
        await caller("PROMPT_ONLY", "m")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    content = call_kwargs["messages"][0]["content"]
    assert content == "PROMPT_ONLY"


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
    "exc,expected",
    [(exc, expected) for exc, expected, _ in IS_SPEND_LIMIT_CASES],
    ids=[case_id for _, _, case_id in IS_SPEND_LIMIT_CASES],
)
def test_is_spend_limit_table(exc: Exception, expected: bool) -> None:
    assert is_spend_limit(exc) is expected
