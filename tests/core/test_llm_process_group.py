"""A hung CLI call is killed together with every process it started.

2026-09-29 review: the timeout killed the direct process only; a child it had
spawned survived as an orphan (PPID 1). Real processes here, no mocks: a fake
`claude` script that starts `sleep` and hangs."""

import os
import time

import pytest
from moonlighter.core import llm


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def test_a_timed_out_cli_call_takes_its_children_down_too(tmp_path, monkeypatch):
    child_pid_file = tmp_path / "child.pid"
    fake_cli = tmp_path / "claude"
    fake_cli.write_text(f"#!/bin/bash\nsleep 30 &\necho $! > {child_pid_file}\nwait\n")
    fake_cli.chmod(0o755)
    monkeypatch.setattr(llm.shutil, "which", lambda name: str(fake_cli))
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))

    # 5 s, not 1: under heavy load the timeout fired before bash had started the
    # child and written its pid, so the test died on a missing child.pid
    # (2026-10-05, load 25-40). The fake CLI hangs for 30 s either way.
    with pytest.raises(RuntimeError, match="did not answer"):
        await llm._call_cli("prompt", "model", timeout_seconds=5)

    child_pid = int(child_pid_file.read_text())
    for _ in range(50):
        if not _is_alive(child_pid):
            break
        time.sleep(0.05)
    assert not _is_alive(child_pid), "the child of the killed CLI survived as an orphan"


async def test_a_timed_out_cursor_call_takes_its_children_down_too(tmp_path, monkeypatch):
    child_pid_file = tmp_path / "child.pid"
    fake_cli = tmp_path / "agent"
    fake_cli.write_text(f"#!/bin/bash\nsleep 30 &\necho $! > {child_pid_file}\nwait\n")
    fake_cli.chmod(0o755)

    def which(name: str) -> str | None:
        return str(fake_cli) if name == "agent" else None

    monkeypatch.setattr(llm.shutil, "which", which)
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(llm, "_cursor_projects_root", lambda: tmp_path / "projects")

    with pytest.raises(RuntimeError, match="did not answer"):
        await llm._call_cursor("prompt", "model", timeout_seconds=1)

    child_pid = int(child_pid_file.read_text())
    for _ in range(50):
        if not _is_alive(child_pid):
            break
        time.sleep(0.05)
    assert not _is_alive(child_pid), "the child of the killed agent survived as an orphan"
