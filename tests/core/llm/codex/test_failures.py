import asyncio
import os
import signal
from unittest.mock import AsyncMock, patch

import pytest

from moonlighter.core.llm import codex
from moonlighter.core.llm.codex import call_codex
from moonlighter.core.llm.spend_limit import is_spend_limit
from tests.core.llm.codex.fake_codex import LOGGED_IN, fake_process


async def test_a_nonzero_exit_names_the_code_and_truncates_the_detail():
    async def create(*argv: str, **launch_options):
        if argv[1:3] == ("login", "status"):
            return fake_process(LOGGED_IN)
        return fake_process(b"", b"E" * 500, code=2)

    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError, match="exited with code 2") as caught,
    ):
        await call_codex("prompt", "gpt-5")
    assert "E" * 300 in str(caught.value)
    assert "E" * 301 not in str(caught.value)


async def test_a_usage_limit_error_still_reads_as_a_spend_limit():
    async def create(*argv: str, **launch_options):
        if argv[1:3] == ("login", "status"):
            return fake_process(LOGGED_IN)
        return fake_process(b"", b"usage_limit_reached: try later", code=1)

    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError) as caught,
    ):
        await call_codex("prompt", "gpt-5")
    assert is_spend_limit(caught.value)


async def test_a_call_that_hangs_is_killed_with_its_process_group():
    hung = fake_process()
    hung.communicate = AsyncMock(side_effect=TimeoutError)

    async def create(*argv: str, **launch_options):
        if argv[1:3] == ("login", "status"):
            return fake_process(LOGGED_IN)
        return hung

    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        patch("moonlighter.core.llm.isolation.os.killpg") as killpg,
        pytest.raises(RuntimeError, match="did not answer within 7"),
    ):
        await call_codex("prompt", "gpt-5", timeout_seconds=7)
    killpg.assert_called_once()
    assert killpg.call_args.args[0] == 4242


async def test_a_login_check_that_hangs_is_killed_too():
    hung = fake_process()
    hung.communicate = AsyncMock(side_effect=TimeoutError)
    with (
        patch(
            "moonlighter.core.llm.codex.asyncio.create_subprocess_exec",
            AsyncMock(return_value=hung),
        ),
        patch("moonlighter.core.llm.isolation.os.killpg") as killpg,
        pytest.raises(RuntimeError, match="did not answer"),
    ):
        await call_codex("prompt", "gpt-5")
    killpg.assert_called_once()


async def test_a_hung_codex_takes_its_children_down_too(tmp_path, monkeypatch):
    """Real processes, no mocks: a fake `codex` that starts `sleep` and hangs."""
    child_pid_file = tmp_path / "child.pid"
    fake_cli = tmp_path / "codex"
    fake_cli.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = "login" ]; then echo "Logged in using ChatGPT"; exit 0; fi\n'
        f"sleep 30 &\necho $! > {child_pid_file}\nwait\n"
    )
    fake_cli.chmod(0o755)
    monkeypatch.undo()
    monkeypatch.setattr(codex.shutil, "which", lambda name: str(fake_cli))
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))

    with pytest.raises(RuntimeError, match="did not answer"):
        await call_codex("prompt", "gpt-5", timeout_seconds=5)

    child_pid = int(child_pid_file.read_text())
    for _ in range(50):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.05)
    pytest.fail("the child of the killed codex survived as an orphan")


async def test_a_hung_login_check_waits_its_own_twenty_seconds_and_kills_the_group():
    hung = fake_process()
    hung.communicate = AsyncMock(side_effect=TimeoutError)
    with (
        patch(
            "moonlighter.core.llm.codex.asyncio.create_subprocess_exec",
            AsyncMock(return_value=hung),
        ),
        patch("moonlighter.core.llm.isolation.os.killpg") as killpg,
        pytest.raises(RuntimeError) as raised,
    ):
        await call_codex("prompt", "gpt-5", timeout_seconds=7)
    assert str(raised.value) == (
        "codex CLI did not answer within 20.0 s — killed "
        "(raise llm_timeout_seconds in config.yaml if your calls are legitimately slow)"
    )
    killpg.assert_called_once_with(4242, signal.SIGKILL)
    hung.wait.assert_awaited_once()


async def test_a_hung_exec_message_is_pinned_word_for_word():
    hung = fake_process()
    hung.communicate = AsyncMock(side_effect=TimeoutError)
    launch = AsyncMock(side_effect=[fake_process(LOGGED_IN), hung])
    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", launch),
        patch("moonlighter.core.llm.isolation.os.killpg") as killpg,
        pytest.raises(RuntimeError) as raised,
    ):
        await call_codex("prompt", "gpt-5", timeout_seconds=7)
    assert str(raised.value) == (
        "codex CLI did not answer within 7 s — killed "
        "(raise llm_timeout_seconds in config.yaml if your calls are legitimately slow)"
    )
    killpg.assert_called_once_with(4242, signal.SIGKILL)


@pytest.mark.parametrize(
    ("stdout", "stderr", "code", "message"),
    [
        (b"", b"boom", 2, "codex CLI exited with code 2: boom"),
        (b"from stdout", b"", 3, "codex CLI exited with code 3: from stdout"),
        (b"from stdout", b"  \n", 3, "codex CLI exited with code 3: from stdout"),
        (b"", b"  padded  \n", 2, "codex CLI exited with code 2: padded"),
        (b"", b"bad \xff byte", 2, "codex CLI exited with code 2: bad � byte"),
        (
            b"",
            b"usage_limit_reached: try later",
            1,
            "codex CLI exited with code 1: usage limit: usage_limit_reached: try later",
        ),
    ],
    ids=[
        "stderr",
        "stdout-fallback",
        "whitespace-stderr-falls-back",
        "stripped",
        "invalid-utf8-is-replaced",
        "usage-limit-prefix",
    ],
)
async def test_an_exit_message_is_pinned_word_for_word(*, stdout, stderr, code, message):
    launch = AsyncMock(side_effect=[fake_process(LOGGED_IN), fake_process(stdout, stderr, code)])
    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", launch),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_codex("prompt", "gpt-5")
    assert str(raised.value) == message
