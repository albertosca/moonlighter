"""The `codex` backend: the Codex CLI on the user's ChatGPT login.

Idea and first implementation: JR2PROJETOS (issue 121). The permission profile is
what the 2026-10-25 canary showed is needed: `--sandbox read-only` blocks writes
and the network but still reads `~/.codex/auth.json` and `~/.ssh`."""

import asyncio
import os
import signal
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.core import llm
from moonlighter.core.config.errors import ConfigError
from moonlighter.core.llm import _call_codex, codex_executable, make_caller
from moonlighter.core.metrics import operation_metrics

LOGGED_IN = b"Logged in using ChatGPT\n"


def _process(stdout: bytes = b"", stderr: bytes = b"", code: int = 0) -> MagicMock:
    process = MagicMock()
    process.returncode = code
    process.pid = 4242
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    process.wait = AsyncMock(return_value=code)
    return process


def _fake_codex(
    answer: str | None, *, login: bytes = LOGGED_IN, login_code: int = 0, login_stderr: bytes = b""
):
    """create_subprocess_exec stand-in: `login status` first, then `exec`, which
    writes `answer` to the `--output-last-message` file the way the real CLI does."""
    calls: list[tuple[tuple[str, ...], dict]] = []
    processes: list[MagicMock] = []

    async def create(*argv: str, **launch_options):
        calls.append((argv, launch_options))
        if argv[1:3] == ("login", "status"):
            process = _process(login, login_stderr, login_code)
        else:
            if answer is not None:
                output = Path(argv[argv.index("--output-last-message") + 1])
                output.write_text(answer)
            process = _process(b"", b"", 0)
        processes.append(process)
        return process

    return create, calls, processes


@pytest.fixture(autouse=True)
def _codex_on_path(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        llm.shutil, "which", lambda name: "/opt/bin/codex" if name == "codex" else None
    )
    monkeypatch.setattr(llm.os.path, "realpath", lambda path: str(path))


async def test_the_answer_is_the_last_message_the_cli_wrote():
    create, calls, _ = _fake_codex("the answer\n")
    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create):
        result = await _call_codex("my prompt", "gpt-5")
    assert result == "the answer\n"
    assert [call[0][1:3] for call in calls] == [
        ("login", "status"),
        ("--ask-for-approval", "never"),
    ]


async def test_the_prompt_goes_over_stdin_and_never_argv():
    create, calls, processes = _fake_codex("ok")
    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create):
        await _call_codex("SECRET-PROMPT", "gpt-5")
    exec_argv, exec_options = calls[1]
    assert all("SECRET-PROMPT" not in argument for argument in exec_argv)
    assert exec_argv[-1] == "-"
    assert processes[1].communicate.call_args.kwargs["input"] == b"SECRET-PROMPT"
    assert exec_options["start_new_session"] is True


async def test_cache_prefix_is_concatenated_before_the_prompt():
    create, _, processes = _fake_codex("ok")
    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create):
        await _call_codex("DYNAMIC", "gpt-5", cache_prefix="STATIC")
    assert processes[1].communicate.call_args.kwargs["input"] == b"STATIC\n\nDYNAMIC"


async def test_the_model_is_forwarded():
    create, calls, _ = _fake_codex("ok")
    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create):
        await _call_codex("prompt", "gpt-5")
    exec_argv = calls[1][0]
    assert exec_argv[exec_argv.index("--model") + 1] == "gpt-5"


async def test_a_claude_model_id_is_refused_before_anything_runs():
    create, calls, _ = _fake_codex("ok")
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError, match=r"llm_model.*eval_model"),
    ):
        await _call_codex("prompt", "claude-sonnet-4-6")
    assert calls == []


async def test_launch_flags_lock_the_agent_down():
    create, calls, _ = _fake_codex("ok")
    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create):
        await _call_codex("prompt", "gpt-5")
    exec_argv = calls[1][0]
    assert exec_argv[1:4] == ("--ask-for-approval", "never", "exec")
    for required in ("--ignore-user-config", "--ephemeral", "--skip-git-repo-check"):
        assert required in exec_argv
    # `--sandbox` selects the old policy, which reads every file; the profile replaces it.
    assert "--sandbox" not in exec_argv
    for forbidden in (
        "--dangerously-bypass-approvals-and-sandbox",
        "--full-auto",
        "--yolo",
        "--search",
    ):
        assert forbidden not in exec_argv
    overrides = [exec_argv[index + 1] for index, flag in enumerate(exec_argv) if flag == "-c"]
    assert 'default_permissions="moonlighter-locked"' in overrides
    assert 'model_provider="openai"' in overrides
    assert 'web_search="disabled"' in overrides
    assert "permissions.moonlighter-locked.network={enabled=false}" in overrides
    disabled = [exec_argv[index + 1] for index, flag in enumerate(exec_argv) if flag == "--disable"]
    for feature in ("shell_tool", "unified_exec", "apps", "plugins", "multi_agent", "hooks"):
        assert feature in disabled


async def test_the_profile_denies_everything_but_the_workspace_and_the_binary():
    create, calls, _ = _fake_codex("ok")
    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create):
        await _call_codex("prompt", "gpt-5")
    exec_argv = calls[1][0]
    profile = next(
        exec_argv[index + 1]
        for index, flag in enumerate(exec_argv)
        if flag == "-c"
        and exec_argv[index + 1].startswith("permissions.moonlighter-locked.filesystem=")
    )
    assert '":root"="deny"' in profile
    assert '":workspace_roots"={"."="read"}' in profile
    assert '"/opt/bin"="read"' in profile
    assert "write" not in profile
    assert "~" not in profile


def test_the_profile_also_grants_the_directory_the_symlink_resolves_to(monkeypatch):
    monkeypatch.setattr(llm.os.path, "realpath", lambda path: "/opt/Caskroom/codex/1/bin/codex")
    joined = " ".join(llm._codex_permission_args("/opt/bin/codex"))
    assert '"/opt/bin"="read"' in joined
    assert '"/opt/Caskroom/codex/1/bin"="read"' in joined


async def test_the_environment_drops_every_api_credential(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.setenv(name, "must-not-reach-the-child")
    monkeypatch.setenv("KEEP_ME", "yes")
    create, calls, _ = _fake_codex("ok")
    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create):
        await _call_codex("prompt", "gpt-5")
    for _, launch_options in calls:
        environment = launch_options["env"]
        assert "ANTHROPIC_API_KEY" not in environment
        assert "OPENAI_API_KEY" not in environment
        assert "CODEX_API_KEY" not in environment
        assert "OPENAI_BASE_URL" not in environment
        assert environment["KEEP_ME"] == "yes"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (b"Not logged in\n", 1),
        (b"Logged in using an API key\n", 0),
        (b"Logged in using ChatGPT\n", 1),
    ],
)
async def test_anything_but_a_chatgpt_login_is_refused(status, code):
    create, calls, _ = _fake_codex("ok", login=status, login_code=code)
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError, match="codex login"),
    ):
        await _call_codex("prompt", "gpt-5")
    assert len(calls) == 1, "the agent must not start without a ChatGPT login"


async def test_a_missing_binary_says_how_to_install_and_log_in(monkeypatch):
    monkeypatch.setattr(llm.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match=r"`codex` CLI was not found.*codex login"):
        await _call_codex("prompt", "gpt-5")


async def test_a_nonzero_exit_names_the_code_and_truncates_the_detail():
    async def create(*argv: str, **launch_options):
        if argv[1:3] == ("login", "status"):
            return _process(LOGGED_IN)
        return _process(b"", b"E" * 500, code=2)

    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError, match="exited with code 2") as caught,
    ):
        await _call_codex("prompt", "gpt-5")
    assert "E" * 300 in str(caught.value)
    assert "E" * 301 not in str(caught.value)


async def test_a_usage_limit_error_still_reads_as_a_spend_limit():
    async def create(*argv: str, **launch_options):
        if argv[1:3] == ("login", "status"):
            return _process(LOGGED_IN)
        return _process(b"", b"usage_limit_reached: try later", code=1)

    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError) as caught,
    ):
        await _call_codex("prompt", "gpt-5")
    assert llm.is_spend_limit(caught.value)


@pytest.mark.parametrize("answer", [None, "", "   \n"])
async def test_no_answer_is_an_error_not_an_empty_string(answer):
    create, _, _ = _fake_codex(answer)
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError, match=r"no final response|empty"),
    ):
        await _call_codex("prompt", "gpt-5")


async def test_each_call_gets_a_private_workdir_that_is_gone_afterwards(tmp_path):
    seen: list[Path] = []

    async def create(*argv: str, **launch_options):
        workdir = Path(launch_options["cwd"])
        seen.append(workdir)
        assert workdir.stat().st_mode & 0o777 == 0o700
        assert workdir.parent == tmp_path / "home"
        if argv[1:3] == ("login", "status"):
            return _process(LOGGED_IN)
        Path(argv[argv.index("--output-last-message") + 1]).write_text("ok")
        return _process()

    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create):
        await _call_codex("first", "gpt-5")
        await _call_codex("second", "gpt-5")
    assert len(set(seen)) == 2
    assert not any(path.exists() for path in seen)


async def test_the_workdir_is_removed_when_the_call_fails():
    seen: list[Path] = []

    async def create(*argv: str, **launch_options):
        seen.append(Path(launch_options["cwd"]))
        return _process(b"Not logged in", b"", 1)

    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError),
    ):
        await _call_codex("prompt", "gpt-5")
    assert seen
    assert not seen[0].exists()


async def test_a_call_that_hangs_is_killed_with_its_process_group():
    hung = _process()
    hung.communicate = AsyncMock(side_effect=TimeoutError)

    async def create(*argv: str, **launch_options):
        if argv[1:3] == ("login", "status"):
            return _process(LOGGED_IN)
        return hung

    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        patch("moonlighter.core.llm.os.killpg") as killpg,
        pytest.raises(RuntimeError, match="did not answer within 7"),
    ):
        await _call_codex("prompt", "gpt-5", timeout_seconds=7)
    killpg.assert_called_once()
    assert killpg.call_args.args[0] == 4242


async def test_a_login_check_that_hangs_is_killed_too():
    hung = _process()
    hung.communicate = AsyncMock(side_effect=TimeoutError)
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", AsyncMock(return_value=hung)),
        patch("moonlighter.core.llm.os.killpg") as killpg,
        pytest.raises(RuntimeError, match="did not answer"),
    ):
        await _call_codex("prompt", "gpt-5")
    killpg.assert_called_once()


def test_codex_executable_is_the_one_on_path():
    assert codex_executable() == "/opt/bin/codex"


def test_make_caller_codex_delegates_with_the_configured_timeout():
    delegate = AsyncMock(return_value="x")
    with patch("moonlighter.core.llm._call_codex", delegate):
        caller = make_caller({"llm_backend": "codex", "llm_timeout_seconds": 42})
        result = asyncio.run(caller("prompt", "gpt-5", "prefix"))
    assert result == "x"
    delegate.assert_awaited_once_with("prompt", "gpt-5", "prefix", timeout_seconds=42)


def test_make_caller_codex_defaults_to_the_shared_timeout():
    delegate = AsyncMock(return_value="x")
    with patch("moonlighter.core.llm._call_codex", delegate):
        asyncio.run(make_caller({"llm_backend": "codex"})("prompt", "gpt-5"))
    assert delegate.await_args.kwargs["timeout_seconds"] == llm.DEFAULTS["llm_timeout_seconds"]


def test_an_unknown_backend_still_lists_codex():
    with pytest.raises(ConfigError, match="cli, api, cursor, codex"):
        make_caller({"llm_backend": "nope"})


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
    monkeypatch.setattr(llm.shutil, "which", lambda name: str(fake_cli))
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))

    with pytest.raises(RuntimeError, match="did not answer"):
        await _call_codex("prompt", "gpt-5", timeout_seconds=5)

    child_pid = int(child_pid_file.read_text())
    for _ in range(50):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail("the child of the killed codex survived as an orphan")


@pytest.mark.parametrize("model", ["claude-sonnet-4-6", "CLAUDE-X", "", "   "])
async def test_a_refused_model_quotes_the_setting_and_the_model_it_got(model):
    create, calls, _ = _fake_codex("ok")
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError) as raised,
    ):
        await _call_codex("prompt", model)
    assert str(raised.value) == (
        "llm_backend 'codex' needs a non-Claude llm_model and eval_model in config.yaml, "
        f"got {model!r}. Set both to a model your ChatGPT plan offers."
    )
    assert calls == []


async def test_a_missing_binary_message_is_pinned_word_for_word(monkeypatch):
    monkeypatch.setattr(llm.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError) as raised:
        await _call_codex("prompt", "gpt-5")
    assert str(raised.value) == (
        "the `codex` CLI was not found on PATH. Install it "
        "(`brew install --cask codex`) and run `codex login` with your ChatGPT account."
    )


async def test_a_login_refusal_message_is_pinned_word_for_word():
    create, _, _ = _fake_codex("ok", login=b"Not logged in\n", login_code=1)
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError) as raised,
    ):
        await _call_codex("prompt", "gpt-5")
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
    create, calls, _ = _fake_codex("the answer", login=login, login_stderr=login_stderr)
    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create):
        result = await _call_codex("prompt", "gpt-5")
    assert result == "the answer"
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (None, "codex CLI wrote no final response"),
        ("", "codex CLI returned an empty final response"),
        ("   \n", "codex CLI returned an empty final response"),
    ],
)
async def test_a_missing_answer_message_is_pinned_word_for_word(answer, message):
    create, _, _ = _fake_codex(answer)
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError) as raised,
    ):
        await _call_codex("prompt", "gpt-5")
    assert str(raised.value) == message


async def test_a_hung_login_check_waits_its_own_twenty_seconds_and_kills_the_group():
    hung = _process()
    hung.communicate = AsyncMock(side_effect=TimeoutError)
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", AsyncMock(return_value=hung)),
        patch("moonlighter.core.llm.os.killpg") as killpg,
        pytest.raises(RuntimeError) as raised,
    ):
        await _call_codex("prompt", "gpt-5", timeout_seconds=7)
    assert str(raised.value) == (
        "codex CLI did not answer within 20.0 s — killed "
        "(raise llm_timeout_seconds in config.yaml if your calls are legitimately slow)"
    )
    killpg.assert_called_once_with(4242, signal.SIGKILL)
    hung.wait.assert_awaited_once()


async def test_a_hung_exec_message_is_pinned_word_for_word():
    hung = _process()
    hung.communicate = AsyncMock(side_effect=TimeoutError)
    launch = AsyncMock(side_effect=[_process(LOGGED_IN), hung])
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", launch),
        patch("moonlighter.core.llm.os.killpg") as killpg,
        pytest.raises(RuntimeError) as raised,
    ):
        await _call_codex("prompt", "gpt-5", timeout_seconds=7)
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
    launch = AsyncMock(side_effect=[_process(LOGGED_IN), _process(stdout, stderr, code)])
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", launch),
        pytest.raises(RuntimeError) as raised,
    ):
        await _call_codex("prompt", "gpt-5")
    assert str(raised.value) == message


async def test_the_login_check_and_the_exec_launch_exactly_these_argvs():
    create, calls, processes = _fake_codex("ok")
    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create):
        await _call_codex("prompt", "gpt-5")
    (login_argv, login_options), (exec_argv, exec_options) = calls
    workdir = login_options["cwd"]
    features = (
        "shell_tool",
        "unified_exec",
        "apps",
        "plugins",
        "remote_plugin",
        "multi_agent",
        "hooks",
        "browser_use",
        "browser_use_external",
        "computer_use",
        "image_generation",
        "in_app_browser",
        "skill_search",
        "tool_suggest",
    )
    assert login_argv == ("/opt/bin/codex", "login", "status")
    assert processes[0].communicate.call_args.kwargs["input"] == b""
    assert exec_argv == (
        "/opt/bin/codex",
        "--ask-for-approval",
        "never",
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "-c",
        'model_provider="openai"',
        "-c",
        'web_search="disabled"',
        "-c",
        'default_permissions="moonlighter-locked"',
        "-c",
        (
            'permissions.moonlighter-locked.filesystem={":minimal"="read",":root"="deny",'
            '"/opt/bin"="read",":workspace_roots"={"."="read"}}'
        ),
        "-c",
        "permissions.moonlighter-locked.network={enabled=false}",
        *(part for feature in features for part in ("--disable", feature)),
        "--model",
        "gpt-5",
        "--output-last-message",
        str(Path(workdir) / "final-message.txt"),
        "-",
    )
    for options in (login_options, exec_options):
        assert set(options) == {"stdin", "stdout", "stderr", "env", "cwd", "start_new_session"}
        assert options["stdin"] == asyncio.subprocess.PIPE
        assert options["stdout"] == asyncio.subprocess.PIPE
        assert options["stderr"] == asyncio.subprocess.PIPE
        assert options["start_new_session"] is True
        assert options["cwd"] == workdir


def test_the_permission_args_are_pinned_with_both_binary_directories(monkeypatch):
    monkeypatch.setattr(llm.os.path, "realpath", lambda path: "/opt/Caskroom/codex/1/bin/codex")
    assert llm._codex_permission_args("/opt/bin/codex") == [
        "-c",
        'default_permissions="moonlighter-locked"',
        "-c",
        (
            'permissions.moonlighter-locked.filesystem={":minimal"="read",":root"="deny",'
            '"/opt/bin"="read","/opt/Caskroom/codex/1/bin"="read",":workspace_roots"={"."="read"}}'
        ),
        "-c",
        "permissions.moonlighter-locked.network={enabled=false}",
    ]


async def test_the_private_workdir_is_named_for_codex_under_moonlighter_home(tmp_path):
    create, calls, _ = _fake_codex("ok")
    with patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create):
        await _call_codex("prompt", "gpt-5")
    workdir = Path(calls[0][1]["cwd"])
    assert workdir.name.startswith("codex-")
    assert workdir.parent == tmp_path / "home"


async def test_a_codex_call_that_answers_records_one_call():
    create, _, _ = _fake_codex("ok")
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        operation_metrics("pin") as metrics,
    ):
        await _call_codex("prompt", "gpt-5")
    assert metrics.calls == 1


async def test_a_codex_call_that_exits_nonzero_records_one_call():
    launch = AsyncMock(side_effect=[_process(LOGGED_IN), _process(b"", b"boom", 2)])
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", launch),
        operation_metrics("pin") as metrics,
        pytest.raises(RuntimeError),
    ):
        await _call_codex("prompt", "gpt-5")
    assert metrics.calls == 1


def test_a_refused_model_records_no_call_and_creates_no_workdir(tmp_path):
    with operation_metrics("pin") as metrics, pytest.raises(RuntimeError):
        asyncio.run(_call_codex("prompt", "claude-sonnet-4-6"))
    assert metrics.calls == 0
    assert not (tmp_path / "home").exists()


def test_a_missing_codex_binary_records_no_call_and_creates_no_workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(llm.shutil, "which", lambda name: None)
    with operation_metrics("pin") as metrics, pytest.raises(RuntimeError):
        asyncio.run(_call_codex("prompt", "gpt-5"))
    assert metrics.calls == 0
    assert not (tmp_path / "home").exists()


async def test_a_failed_workdir_cleanup_is_logged_and_the_answer_survives(caplog):
    create, calls, _ = _fake_codex("the answer")
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        patch("moonlighter.core.llm.shutil.rmtree", side_effect=OSError("busy")),
        caplog.at_level("ERROR"),
    ):
        result = await _call_codex("prompt", "gpt-5")
    assert result == "the answer"
    assert f"cursor cleanup failed for {calls[0][1]['cwd']}" in caplog.messages


async def test_a_cleanup_that_raises_still_records_the_call():
    create, _, _ = _fake_codex("ok")
    with (
        patch("moonlighter.core.llm.asyncio.create_subprocess_exec", create),
        patch("moonlighter.core.llm._remove_quietly", side_effect=RuntimeError("cleanup")),
        operation_metrics("pin") as metrics,
        pytest.raises(RuntimeError, match=r"^cleanup$"),
    ):
        await _call_codex("prompt", "gpt-5")
    assert metrics.calls == 1
