import asyncio
from pathlib import Path
from unittest.mock import patch

from moonlighter.core.llm.codex import call_codex
from tests.core.llm.codex.fake_codex import fake_codex


async def test_launch_flags_lock_the_agent_down():
    create, calls, _ = fake_codex("ok")
    with patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create):
        await call_codex("prompt", "gpt-5")
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
    create, calls, _ = fake_codex("ok")
    with patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create):
        await call_codex("prompt", "gpt-5")
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


async def test_the_environment_drops_every_api_credential(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.setenv(name, "must-not-reach-the-child")
    monkeypatch.setenv("KEEP_ME", "yes")
    create, calls, _ = fake_codex("ok")
    with patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create):
        await call_codex("prompt", "gpt-5")
    for _, launch_options in calls:
        environment = launch_options["env"]
        assert "ANTHROPIC_API_KEY" not in environment
        assert "OPENAI_API_KEY" not in environment
        assert "CODEX_API_KEY" not in environment
        assert "OPENAI_BASE_URL" not in environment
        assert environment["KEEP_ME"] == "yes"


async def test_the_login_check_and_the_exec_launch_exactly_these_argvs():
    create, calls, processes = fake_codex("ok")
    with patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create):
        await call_codex("prompt", "gpt-5")
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
