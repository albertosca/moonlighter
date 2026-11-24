"""moonlighter's MCP tools, called from inside opencode (e2e, local fake provider).

The registration `moonlighter init` writes (`MCP_ENTRY`) is the one under test,
with the command swapped for this checkout's entry point so the run is offline.
A scripted fake model asks for `get_pipeline`, then answers DONE; the test
reads opencode's own event stream and the second request the fake receives.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from moonlighter.core.llm.opencode import opencode_executable
from moonlighter.opencode_registration import MCP_ENTRY
from tests.core.llm.fake_openai_provider import FakeProvider, provider_config, text, tool_call

pytestmark = pytest.mark.e2e

_ALLOW_ALL = [{"action": "*", "resource": "*", "effect": "allow"}]
_RUN_TIMEOUT_SECONDS = 180
_RUN_ARGUMENTS = ["run", "--standalone", "--archived", "--title", "call", "-m", "fake/echo"]


def _pipeline_tool(names: list[str]) -> tuple[str, str] | None:
    """`get_pipeline`, once the server has connected; None asks the fake to make opencode retry."""
    matches = [name for name in names if name.endswith("get_pipeline")]
    return (matches[0], "{}") if matches else None


def _environment(root: Path, config_file: Path) -> dict[str, str]:
    """The developer's environment in a scratch HOME/XDG world, under the given config."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("OPENCODE_", "XDG_", "MOONLIGHTER_"))
        and name not in {"PWD", "OLDPWD"}
    }
    environment["HOME"] = str(root / "home")
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        environment[name] = str(root / "xdg" / name.lower())
    config_directory = root / "config"
    config_directory.mkdir()
    environment.update(
        {
            "OPENCODE_CONFIG": str(config_file),
            "OPENCODE_CONFIG_DIR": str(config_directory),
            "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
            "OPENCODE_DISABLE_CLAUDE_CODE": "1",
            "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "1",
            "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1",
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
        }
    )
    return environment


def _config(base_url: str, moonlighter_home: Path) -> dict[str, Any]:
    server = {
        **MCP_ENTRY,
        "command": [str(Path(sys.executable).parent / "moonlighter")],
        "environment": {"MOONLIGHTER_HOME": str(moonlighter_home)},
    }
    return {
        "share": "disabled",
        "permissions": _ALLOW_ALL,
        "providers": provider_config(base_url),
        "mcp": {"servers": {"moonlighter": server}},
    }


def _events(stdout: bytes) -> list[dict[str, Any]]:
    lines = stdout.decode(errors="replace").splitlines()
    return [json.loads(line) for line in lines if line.strip().startswith("{")]


def test_opencode_runs_get_pipeline_from_the_moonlighter_server(tmp_path):
    executable = opencode_executable()
    if executable is None:
        pytest.fail(
            "the `opencode` CLI was not found on PATH. Install it from https://opencode.ai."
        )
    root = tmp_path.resolve()
    workdir = root / "workdir"
    workdir.mkdir()
    with FakeProvider([tool_call(_pipeline_tool), text("DONE")]) as provider:
        config_file = root / "opencode.json"
        config_file.write_text(json.dumps(_config(provider.base_url, root / "moonlighter-home")))
        result = subprocess.run(  # noqa: S603 - fixed argv; the executable comes from PATH
            [executable, *_RUN_ARGUMENTS, "--format", "json"],
            input=b"Check my moonlighter pipeline.",
            cwd=workdir,
            env=_environment(root, config_file),
            capture_output=True,
            timeout=_RUN_TIMEOUT_SECONDS,
            check=False,
        )
    events = _events(result.stdout)
    assert result.returncode == 0, (result.stderr.decode(errors="replace")[-2000:], events)
    tool_uses = [event["part"] for event in events if event.get("type") == "tool_use"]
    assert [
        (part["tool"].endswith("get_pipeline"), part["state"]["status"]) for part in tool_uses
    ] == [(True, "completed")], (
        [event.get("type") for event in events],
        [len(request.get("tools") or []) for request in provider.requests],
    )
    sent_back = [
        message for message in provider.requests[-1]["messages"] if message.get("role") == "tool"
    ]
    assert sent_back, "positive control: opencode never sent the tool result back to the model"
    assert "Setup Warnings" in str(sent_back[0]["content"]), sent_back
    assert (
        "".join(event["part"]["text"] for event in events if event.get("type") == "text").strip()
        == "DONE"
    )
