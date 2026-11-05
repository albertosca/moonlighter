"""The locked `codex exec` command line: its permission profile and the features it disables."""

import json
import os
from pathlib import Path

# The canary on Codex CLI 0.164.0 (2026-10-25): `--sandbox read-only` blocks
# writes and the network but still reads every file the user can, including
# `~/.codex/auth.json` (the ChatGPT token) and `~/.ssh`. A permission profile
# denies the whole filesystem except the call's own workdir, and `--sandbox` is
# never passed: it selects the old policy and the profile is ignored. Each
# feature below adds a tool or a connector the scoring prompts have no use for;
# the apps connectors live outside the filesystem sandbox, so they go too.
_CODEX_PROFILE = "moonlighter-locked"
_CODEX_DISABLED_FEATURES: tuple[str, ...] = (
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


def _codex_permission_args(executable: str) -> list[str]:
    """`-c` overrides for the locked profile.

    Besides the workdir, the profile grants read on the directory of the binary
    and of the file a symlink resolves to: the CLI starts itself again inside the
    sandbox to load its instructions, and with only `:minimal` readable that
    start fails with `Operation not permitted`.
    """
    binary_directories = dict.fromkeys(
        [str(Path(executable).parent), str(Path(os.path.realpath(executable)).parent)]
    )
    entries = [f'{json.dumps(":minimal")}="read"', f'{json.dumps(":root")}="deny"']
    entries.extend(f'{json.dumps(directory)}="read"' for directory in binary_directories)
    entries.append(f'{json.dumps(":workspace_roots")}={{"."="read"}}')
    return [
        "-c",
        f'default_permissions="{_CODEX_PROFILE}"',
        "-c",
        f"permissions.{_CODEX_PROFILE}.filesystem={{{','.join(entries)}}}",
        "-c",
        f"permissions.{_CODEX_PROFILE}.network={{enabled=false}}",
    ]


def codex_exec_argv(executable: str, model: str, output: Path) -> list[str]:
    """The `codex exec` argv, ending `--model <model> --output-last-message <output> -`.

    The locked profile stands in for `--sandbox`, and every feature in
    `_CODEX_DISABLED_FEATURES` is disabled. The prompt itself never enters argv.
    """
    argv = [
        executable,
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
        *_codex_permission_args(executable),
    ]
    for feature in _CODEX_DISABLED_FEATURES:
        argv.extend(["--disable", feature])
    argv.extend(["--model", model, "--output-last-message", str(output), "-"])
    return argv
