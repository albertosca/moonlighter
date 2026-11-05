from unittest.mock import patch

import pytest
from moonlighter.core.llm import codex
from moonlighter.core.llm.codex import call_codex, codex_executable

from tests.core.llm.codex.fake_codex import fake_codex


async def test_a_claude_model_id_is_refused_before_anything_runs():
    create, calls, _ = fake_codex("ok")
    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError, match=r"llm_model.*eval_model"),
    ):
        await call_codex("prompt", "claude-sonnet-4-6")
    assert calls == []


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (b"Not logged in\n", 1),
        (b"Logged in using an API key\n", 0),
        (b"Logged in using ChatGPT\n", 1),
    ],
)
async def test_anything_but_a_chatgpt_login_is_refused(status, code):
    create, calls, _ = fake_codex("ok", login=status, login_code=code)
    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError, match="codex login"),
    ):
        await call_codex("prompt", "gpt-5")
    assert len(calls) == 1, "the agent must not start without a ChatGPT login"


async def test_a_missing_binary_says_how_to_install_and_log_in(monkeypatch):
    monkeypatch.setattr(codex.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match=r"`codex` CLI was not found.*codex login"):
        await call_codex("prompt", "gpt-5")


def test_codex_executable_is_the_one_on_path():
    assert codex_executable() == "/opt/bin/codex"


@pytest.mark.parametrize("model", ["claude-sonnet-4-6", "CLAUDE-X", "", "   "])
async def test_a_refused_model_quotes_the_setting_and_the_model_it_got(model):
    create, calls, _ = fake_codex("ok")
    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_codex("prompt", model)
    assert str(raised.value) == (
        "llm_backend 'codex' needs a non-Claude llm_model and eval_model in config.yaml, "
        f"got {model!r}. Set both to a model your ChatGPT plan offers."
    )
    assert calls == []


async def test_a_missing_binary_message_is_pinned_word_for_word(monkeypatch):
    monkeypatch.setattr(codex.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError) as raised:
        await call_codex("prompt", "gpt-5")
    assert str(raised.value) == (
        "the `codex` CLI was not found on PATH. Install it "
        "(`brew install --cask codex`) and run `codex login` with your ChatGPT account."
    )


async def test_a_login_refusal_message_is_pinned_word_for_word():
    create, _, _ = fake_codex("ok", login=b"Not logged in\n", login_code=1)
    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_codex("prompt", "gpt-5")
    assert str(raised.value) == (
        "llm_backend 'codex' needs a ChatGPT login (an API key is not used). "
        "Run `codex login` and sign in with your ChatGPT account."
    )


@pytest.mark.parametrize(
    ("login", "login_stderr"),
    [
        (b"\xff Logged in using ChatGPT\n", b""),
        (b"", b"Logged in using ChatGPT\n"),
        (b"LOGGED IN USING CHATGPT\n", b""),
    ],
    ids=["invalid-utf8-is-replaced", "stderr-counts", "case-is-ignored"],
)
async def test_a_chatgpt_login_is_recognised_however_it_is_printed(login, login_stderr):
    create, calls, _ = fake_codex("the answer", login=login, login_stderr=login_stderr)
    with patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create):
        result = await call_codex("prompt", "gpt-5")
    assert result == "the answer"
    assert len(calls) == 2
