"""The wizard adds moonlighter to opencode's global config, and never rewrites what it cannot read."""

import json
from typing import Any

import pytest

from moonlighter.opencode_registration import (
    MCP_ENTRY,
    opencode_config_path,
    register_in_opencode,
    registration_snippet,
)

REGISTERED = {"mcp": {"servers": {"moonlighter": MCP_ENTRY}}}


@pytest.fixture
def target(tmp_path):
    return tmp_path / "opencode" / "opencode.json"


@pytest.fixture
def plain_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENCODE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def test_the_default_path_is_under_the_home_config(plain_environment, tmp_path):
    assert opencode_config_path() == tmp_path / "home" / ".config" / "opencode" / "opencode.json"


def test_xdg_config_home_moves_the_path(plain_environment, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert opencode_config_path() == tmp_path / "xdg" / "opencode" / "opencode.json"


def test_opencode_config_dir_wins_and_is_expanded(plain_environment, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", "~/custom")
    assert opencode_config_path() == tmp_path / "home" / "custom" / "opencode.json"


def test_a_missing_file_is_created_with_the_entry(target):
    registration = register_in_opencode(target)
    assert registration.written
    assert json.loads(target.read_text()) == {
        "$schema": "https://opencode.ai/config.json",
        **REGISTERED,
    }


def test_an_existing_file_keeps_every_key_and_gets_a_backup(target):
    original: dict[str, Any] = {
        "theme": "x",
        "mcp": {
            "servers": {"other": {"type": "remote", "url": "https://x"}},
            "timeout": {"startup": 5},
        },
    }
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(original))
    before = target.read_bytes()
    registration = register_in_opencode(target)
    assert registration.written
    written = json.loads(target.read_text())
    assert written["theme"] == "x"
    assert written["mcp"]["timeout"] == {"startup": 5}
    assert written["mcp"]["servers"] == {**original["mcp"]["servers"], "moonlighter": MCP_ENTRY}
    assert target.with_name("opencode.json.bak").read_bytes() == before
    assert str(target.with_name("opencode.json.bak")) in registration.reason


def test_an_existing_file_without_mcp_gets_the_block(target):
    target.parent.mkdir(parents=True)
    target.write_text('{"theme": "x"}')
    assert register_in_opencode(target).written
    assert json.loads(target.read_text()) == {"theme": "x", **REGISTERED}


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b'{\n  // mine\n  "theme": "x"\n}', "not plain JSON"),
        (b'{"theme": "x",}', "not plain JSON"),
        (b'{"theme": "\xff"}', "not plain JSON"),
        (b'["x"]', "not an object"),
        (b'{"mcp": "x"}', "not an object"),
        (b'{"mcp": {"servers": ["x"]}}', "not an object"),
        (b'{"mcp": {"other": {"type": "local", "command": ["x"]}}}', "flat"),
        (b'{"mcp": {"servers": {"moonlighter": {"type": "local"}}}}', "already registers"),
        (b'{"mcp": {"moonlighter": {"type": "local", "command": ["x"]}}}', "already registers"),
    ],
    ids=[
        "comment",
        "trailing-comma",
        "invalid-utf8",
        "top-level-list",
        "mcp-string",
        "servers-list",
        "flat-form",
        "already-canonical",
        "already-flat",
    ],
)
def test_a_file_it_cannot_safely_edit_is_left_untouched(target, content, reason):
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    registration = register_in_opencode(target)
    assert not registration.written
    assert reason in registration.reason
    assert target.read_bytes() == content
    assert not target.with_name("opencode.json.bak").exists()


@pytest.mark.parametrize("with_json", [True, False], ids=["beside-json", "alone"])
def test_a_jsonc_config_is_never_edited(target, with_json):
    target.parent.mkdir(parents=True)
    jsonc = target.with_suffix(".jsonc")
    jsonc.write_text('{"theme": "x"}')
    if with_json:
        target.write_text('{"theme": "y"}')
    registration = register_in_opencode(target)
    assert not registration.written
    assert "JSONC" in registration.reason
    assert jsonc.read_text() == '{"theme": "x"}'
    assert target.exists() is with_json
    assert not with_json or target.read_text() == '{"theme": "y"}'


def test_the_snippet_is_the_canonical_entry():
    assert json.loads(registration_snippet()) == REGISTERED
    assert MCP_ENTRY == {
        "type": "local",
        "command": ["uvx", "moonlighter"],
        "protocol": "2026-07-28",
    }
