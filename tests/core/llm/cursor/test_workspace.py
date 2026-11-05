import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from moonlighter.core.llm.cursor import call_cursor

from tests.core.llm.fake_processes import cursor_process


async def test_call_cursor_workspace_is_a_private_directory_per_call(tmp_path, monkeypatch):
    """Two calls in one home never share a workdir, and each directory is gone
    after the call. Mode is recorded while the process is starting: cleanup
    removes the directory before this function resumes.
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    seen: list[tuple[Path, str]] = []

    def start(*positional_arguments: object, **keyword_arguments: object) -> MagicMock:
        workdir = Path(str(keyword_arguments["cwd"]))
        seen.append((workdir, oct(workdir.stat().st_mode)[-3:]))
        return cursor_process()

    with patch(
        "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", side_effect=start
    ) as mock_exec:
        await call_cursor("first line\nTOKEN_ONE", "claude-haiku-4-5-20251001")
        await call_cursor("first line\nTOKEN_TWO", "claude-haiku-4-5-20251001")

    assert len(seen) == 2
    first, second = seen
    assert first[0] != second[0]
    assert first[0].parent == tmp_path
    assert second[0].parent == tmp_path
    assert first[1] == "700"
    assert second[1] == "700"
    assert not first[0].exists()
    assert not second[0].exists()
    for call in mock_exec.call_args_list:
        positional_arguments = call.args
        assert (
            positional_arguments[positional_arguments.index("--workspace") + 1]
            == call.kwargs["cwd"]
        )


async def test_call_cursor_writes_read_denies_before_the_subprocess(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    written: dict[str, str] = {}

    def start(*positional_arguments: object, **keyword_arguments: object) -> MagicMock:
        workdir = Path(str(keyword_arguments["cwd"]))
        written["text"] = (workdir / ".cursor" / "cli.json").read_text()
        written["path"] = str(workdir)
        return cursor_process()

    with patch("moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", side_effect=start):
        await call_cursor("prompt", "model")

    assert json.loads(written["text"]) == {
        "permissions": {"allow": [], "deny": ["Read(/**)", "Read(~/**)"]},
    }
    assert '"allow": []' in written["text"]
    assert not Path(written["path"]).exists()  # noqa: ASYNC240 - checked after the call returned; nothing else runs on the loop


async def test_parallel_cursor_calls_keep_their_own_permissions_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    seen: list[Path] = []

    async def start(*positional_arguments: object, **keyword_arguments: object) -> MagicMock:
        workdir = Path(str(keyword_arguments["cwd"]))
        seen.append(workdir)
        permissions = (workdir / ".cursor" / "cli.json").read_text()
        process = cursor_process()

        async def communicate(input: object = None) -> tuple[bytes, bytes]:  # noqa: A002 - mirrors Process.communicate(input=...)
            await asyncio.sleep(0.05)
            assert (workdir / ".cursor" / "cli.json").read_text() == permissions
            return b"ok", b""

        process.communicate = communicate
        return process

    with patch("moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", side_effect=start):
        await asyncio.gather(
            call_cursor("first line\nTOKEN_ONE", "model"),
            call_cursor("first line\nTOKEN_TWO", "model"),
        )

    assert len(seen) == 2
    assert seen[0] != seen[1]
    assert not seen[0].exists()
    assert not seen[1].exists()


def test_call_cursor_creates_no_workdir_when_agent_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    with (
        patch("moonlighter.core.llm.cursor.shutil.which", return_value=None),
        pytest.raises(RuntimeError),
    ):
        asyncio.run(call_cursor("prompt", "model"))
    assert not (tmp_path / "home").exists()


async def test_call_cursor_permissions_file_is_pinned_byte_for_byte(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    written: list[str] = []

    def start(*positional_arguments: object, **keyword_arguments: object) -> MagicMock:
        workdir = Path(str(keyword_arguments["cwd"]))
        written.append((workdir / ".cursor" / "cli.json").read_text())
        return cursor_process()

    with patch("moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", side_effect=start):
        await call_cursor("prompt", "model")
    assert written == ['{"permissions": {"allow": [], "deny": ["Read(/**)", "Read(~/**)"]}}\n']


async def test_call_cursor_workdir_is_named_for_cursor_under_moonlighter_home(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    with patch(
        "moonlighter.core.llm.cursor.asyncio.create_subprocess_exec", return_value=cursor_process()
    ) as launch:
        await call_cursor("prompt", "model")
    workdir = Path(launch.call_args.kwargs["cwd"])
    assert workdir.name.startswith("cursor-")
    assert workdir.parent == tmp_path / "home"
