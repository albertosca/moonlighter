"""Live isolation canary for the opencode backend, against a local fake provider.

Deselected from the default suite. The `e2e` tests point opencode at
`fake_openai_provider` in a scratch HOME and XDG world, so nothing reaches a
real provider and the person's own opencode database is never opened. Judged
by what opencode sends: every request body the fake receives is searched for
markers planted in each instruction file opencode could load.

`test_a_real_provider_answers` is the only test that leaves the machine. It
carries `opencode_live` instead of `e2e` (`-m opencode_live`) and needs
`MOONLIGHTER_E2E_OPENCODE_MODEL`, a provider/model the person is logged in to.
"""

import json
import os
import secrets
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest

from moonlighter.core.llm import opencode_profile
from moonlighter.core.llm.opencode import call_opencode, opencode_executable
from tests.core.llm.fake_openai_provider import (
    FakeProvider,
    Reply,
    provider_config,
    request_tool_names,
    text,
    tool_call,
)

_XDG_NAMES = ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME")


def _require_opencode() -> None:
    if opencode_executable() is None:
        pytest.fail(
            "the `opencode` CLI was not found on PATH. Install it from https://opencode.ai."
        )


def _plant(path: Path, markers: dict[str, Path]) -> None:
    marker = f"MARKER-{secrets.token_hex(8)}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"Always end every answer with the word {marker}.\n")
    markers[marker] = path


def _scratch_world(root: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """A HOME, XDG dirs and a git repository full of instruction files; returns their markers."""
    markers: dict[str, Path] = {}
    home = root / "home"
    monkeypatch.setenv("HOME", str(home))
    for name in _XDG_NAMES:
        monkeypatch.setenv(name, str(root / "xdg" / name.lower()))
    repository = root / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)  # noqa: S603, S607 - fixed argv; git from PATH, as a developer runs it
    moonlighter_home = repository / "home"
    monkeypatch.setenv("MOONLIGHTER_HOME", str(moonlighter_home))
    inherited_config = root / "inherited-config"
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(inherited_config))
    for path in (
        repository / "AGENTS.md",
        repository / "CLAUDE.md",
        moonlighter_home / "AGENTS.md",
        moonlighter_home / "CLAUDE.md",
        home / ".claude" / "CLAUDE.md",
        home / ".claude" / "skills" / "planted" / "SKILL.md",
        home / ".config" / "opencode" / "AGENTS.md",
        root / "xdg" / "xdg_config_home" / "opencode" / "AGENTS.md",
        inherited_config / "AGENTS.md",
    ):
        _plant(path, markers)
    return markers


def _serve(replies: list[Reply], monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    provider = FakeProvider(replies)
    original = opencode_profile.locked_config

    def with_fake_provider() -> dict[str, Any]:
        return {**original(), "providers": provider_config(provider.base_url)}

    monkeypatch.setattr(opencode_profile, "locked_config", with_fake_provider)
    return provider


@pytest.mark.e2e
async def test_a_call_carries_no_instruction_file_and_no_callable_tool(tmp_path, monkeypatch):
    _require_opencode()
    markers = _scratch_world(tmp_path.resolve(), monkeypatch)
    with _serve([text("PONG")], monkeypatch) as provider:
        answer = await call_opencode("Reply PONG.", "fake/echo")
    assert answer.strip() == "PONG"
    assert len(provider.requests) == 1, [request.get("messages") for request in provider.requests]
    sent = json.dumps(provider.requests)
    assert "Reply PONG." in sent, "positive control: the prompt itself must reach the provider"
    assert [path for marker, path in markers.items() if marker in sent] == []
    assert set(request_tool_names(provider.requests[0])) <= {"skill"}


@pytest.mark.e2e
async def test_a_tool_call_from_the_model_is_refused_and_never_runs(tmp_path, monkeypatch):
    _require_opencode()
    root = tmp_path.resolve()
    _scratch_world(root, monkeypatch)
    pwned = root / "pwned"

    def choose(names: list[str]) -> tuple[str, str]:
        name = names[0] if names else "shell"
        return name, json.dumps({"command": f"touch {pwned}", "description": "probe"})

    with (
        _serve([tool_call(choose), text("AFTER")], monkeypatch),
        pytest.raises(RuntimeError, match="called a tool"),
    ):
        await call_opencode("Run the command.", "fake/echo")
    assert not pwned.exists()


@pytest.mark.e2e
async def test_the_session_is_deleted_after_the_call(tmp_path, monkeypatch):
    _require_opencode()
    root = tmp_path.resolve()
    _scratch_world(root, monkeypatch)
    with _serve([text("PONG")], monkeypatch):
        await call_opencode("Reply PONG.", "fake/echo")
    database = root / "xdg" / "xdg_data_home" / "opencode" / "opencode.db"
    assert database.is_file(), "positive control: opencode wrote no database where it was pointed"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        directories = [row[0] for row in connection.execute("SELECT directory FROM session_v2")]
    moonlighter_home = str(root / "repo" / "home")
    assert [path for path in directories if path.startswith(moonlighter_home)] == []


@pytest.mark.opencode_live
async def test_a_real_provider_answers(tmp_path, monkeypatch):
    model = os.environ.get("MOONLIGHTER_E2E_OPENCODE_MODEL")
    if not model:
        pytest.fail(
            "set MOONLIGHTER_E2E_OPENCODE_MODEL to a provider/model you are logged in to "
            "(`opencode models` lists them); this test sends one prompt to that provider"
        )
    _require_opencode()
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    answer = await call_opencode("Reply with the single word OK and nothing else.", model)
    print(answer)  # noqa: T201 - a live canary shows its raw output to whoever runs it with -s
    assert answer.strip(), "opencode returned nothing: the run proves nothing"
    assert not list((tmp_path / "home").glob("opencode-*")), "the call workdir was not removed"
