"""The locked `opencode run` call: the config it runs under, its environment and its argv.

Measured on opencode 2.4.0 with a local fake provider (2026-11-24): by default a call
carries `~/.claude/CLAUDE.md`, the config directory's `AGENTS.md` and 14 tools. The
deny-all `permissions` remove the tools from the request (`policies` alone let Code
Mode's `execute` run), and the environment below keeps the person's instructions,
skills and config out. A project config would also walk up for every `AGENTS.md`
between the workdir and the repository root, `MOONLIGHTER_HOME`'s own included, so
project config is off (`OPENCODE_DISABLE_PROJECT_CONFIG`) and the locked config
arrives through `OPENCODE_CONFIG`. opencode takes its project directory from `PWD`
over its real cwd, so the inherited `PWD` (the launcher's project) is dropped.
`steps` must never be set: it injects a "MAXIMUM STEPS REACHED" message into the answer.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AGENT_NAME = "moonlighter-call"
_SYSTEM_PROMPT = "Answer the user message directly as plain text."
_DENIED_POLICY_ACTIONS = ("tool.use", "mcp.use", "skill.use", "plugin.use", "websearch.use")
# Pointers the person's shell may carry that would load their own config, or their own
# project, into the call.
_INHERITED_CONFIG_POINTERS = frozenset(
    {
        "OPENCODE_CONFIG",
        "OPENCODE_CONFIG_CONTENT",
        "OPENCODE_CONFIG_DIR",
        "OPENCODE_DISABLE_PROJECT_CONFIG",
        "PWD",
        "OLDPWD",
    }
)


def _deny_everything() -> list[dict[str, str]]:
    return [{"action": "*", "resource": "*", "effect": "deny"}]


def locked_config() -> dict[str, Any]:
    """The `opencode.json` written into each call's workdir; a fresh dict each time."""
    return {
        "$schema": "https://opencode.ai/config.json",
        "share": "disabled",
        "automations": False,
        "permissions": _deny_everything(),
        "agents": {
            AGENT_NAME: {
                "mode": "primary",
                "system": _SYSTEM_PROMPT,
                "permissions": _deny_everything(),
            }
        },
        "policies": [
            {"action": action, "resource": "*", "effect": "deny"}
            for action in _DENIED_POLICY_ACTIONS
        ],
    }


@dataclass(frozen=True)
class CallFiles:
    """What `write_call_files` wrote: the locked config and the empty config directory."""

    config_file: Path
    config_directory: Path


def opencode_environment(inherited: Mapping[str, str], files: CallFiles) -> dict[str, str]:
    """The child's environment: the parent's (provider keys included) under the locked overrides.

    `OPENCODE_CONFIG` names the locked config, `OPENCODE_CONFIG_DIR` an empty
    directory (so the person's global `AGENTS.md`, agents and plugins stay out),
    and project config is off, so no `AGENTS.md` above the workdir is read.
    """
    environment = {
        name: value for name, value in inherited.items() if name not in _INHERITED_CONFIG_POINTERS
    }
    environment.update(
        {
            "OPENCODE_DISABLE_CLAUDE_CODE": "1",
            "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "1",
            "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1",
            "OPENCODE_CONFIG": str(files.config_file),
            "OPENCODE_CONFIG_DIR": str(files.config_directory),
            "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
            "OPENCODE_DISABLE_FILEWATCHER": "1",
        }
    )
    return environment


def opencode_run_argv(executable: str, model: str) -> list[str]:
    """`opencode run` for one call; the prompt arrives on stdin, never here.

    `--title` spares the second model call opencode makes to name a session.
    """
    return [
        executable,
        "run",
        "--standalone",
        "--archived",
        "--title",
        "call",
        "--agent",
        AGENT_NAME,
        "-m",
        model,
        "--format",
        "json",
    ]


def write_call_files(workdir: Path) -> CallFiles:
    """Write the locked `opencode.json` and an empty config directory into `workdir`."""
    config_file = workdir / "opencode.json"
    config_file.write_text(json.dumps(locked_config(), indent=2) + "\n")
    config_directory = workdir / "config"
    config_directory.mkdir(mode=0o700)
    config_directory.chmod(0o700)
    return CallFiles(config_file=config_file, config_directory=config_directory)
