"""How the wizard writes opencode's config: through a symlink, in the person's mode and text."""

import json
import os
import stat
from pathlib import Path

import pytest

from moonlighter.opencode_registration import MCP_ENTRY, register_in_opencode


@pytest.fixture
def target(tmp_path):
    directory = tmp_path / "opencode"
    directory.mkdir()
    return directory / "opencode.json"


def test_a_symlinked_config_is_written_through_and_stays_a_link(tmp_path, target):
    linked_directory = tmp_path / "linked"
    linked_directory.mkdir()
    real_file = linked_directory / "opencode.json"
    real_file.write_text(json.dumps({"theme": "x"}))
    target.symlink_to(real_file)

    registration = register_in_opencode(target)

    assert registration.written
    assert target.is_symlink()
    assert json.loads(real_file.read_text())["mcp"]["servers"]["moonlighter"] == MCP_ENTRY
    assert not (linked_directory / "opencode.json.bak").exists()
    assert json.loads((target.parent / "opencode.json.bak").read_text()) == {"theme": "x"}


def test_the_file_keeps_its_mode(target):
    target.write_text(json.dumps({"theme": "x"}))
    target.chmod(0o644)

    register_in_opencode(target)

    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_non_ascii_text_stays_readable(target):
    target.write_text(json.dumps({"theme": "café"}, ensure_ascii=False), encoding="utf-8")

    register_in_opencode(target)

    assert "café" in target.read_text(encoding="utf-8")


def test_an_existing_backup_is_never_overwritten(target):
    target.write_text(json.dumps({"theme": "new"}))
    earlier_backup = target.with_name("opencode.json.bak")
    earlier_backup.write_text("the person's own backup")

    registration = register_in_opencode(target)

    assert earlier_backup.read_text() == "the person's own backup"
    second_backup = target.with_name("opencode.json.bak.1")
    assert json.loads(second_backup.read_text()) == {"theme": "new"}
    assert str(second_backup) in registration.reason


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_an_unwritable_directory_is_reported_and_leaves_nothing_behind(target):
    target.write_text(json.dumps({"theme": "x"}))
    target.parent.chmod(0o500)
    try:
        registration = register_in_opencode(target)
    finally:
        target.parent.chmod(0o700)

    assert not registration.written
    assert "could not write" in registration.reason
    assert sorted(path.name for path in target.parent.iterdir()) == ["opencode.json"]
    assert json.loads(target.read_text()) == {"theme": "x"}


def test_a_failed_write_removes_its_staging_file(target, monkeypatch):
    target.write_text(json.dumps({"theme": "x"}))

    def refuse(self, destination):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", refuse)
    registration = register_in_opencode(target)

    assert not registration.written
    assert "disk full" in registration.reason
    assert not [path for path in target.parent.iterdir() if path.name.startswith(".opencode-")]
