from pathlib import Path
from unittest.mock import patch

import pytest

from moonlighter.core.llm.codex import call_codex
from tests.core.llm.codex.fake_codex import LOGGED_IN, fake_codex, fake_process, write_final_message


async def test_each_call_gets_a_private_workdir_that_is_gone_afterwards(tmp_path):
    seen: list[Path] = []

    async def create(*argv: str, **launch_options):
        workdir = Path(launch_options["cwd"])
        seen.append(workdir)
        assert workdir.stat().st_mode & 0o777 == 0o700  # noqa: ASYNC240 - a fake launch inspecting its workdir; nothing else runs on the loop
        assert workdir.parent == tmp_path / "home"
        if argv[1:3] == ("login", "status"):
            return fake_process(LOGGED_IN)
        write_final_message(argv, "ok")
        return fake_process()

    with patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create):
        await call_codex("first", "gpt-5")
        await call_codex("second", "gpt-5")
    assert len(set(seen)) == 2
    assert not any(path.exists() for path in seen)


async def test_the_workdir_is_removed_when_the_call_fails():
    seen: list[Path] = []

    async def create(*argv: str, **launch_options):
        seen.append(Path(launch_options["cwd"]))
        return fake_process(b"Not logged in", b"", 1)

    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError),
    ):
        await call_codex("prompt", "gpt-5")
    assert seen
    assert not seen[0].exists()


async def test_the_private_workdir_is_named_for_codex_under_moonlighter_home(tmp_path):
    create, calls, _ = fake_codex("ok")
    with patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create):
        await call_codex("prompt", "gpt-5")
    workdir = Path(calls[0][1]["cwd"])
    assert workdir.name.startswith("codex-")
    assert workdir.parent == tmp_path / "home"


async def test_a_failed_workdir_cleanup_is_logged_and_the_answer_survives(caplog):
    create, calls, _ = fake_codex("the answer")
    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        patch("moonlighter.core.llm.isolation.shutil.rmtree", side_effect=OSError("busy")),
        caplog.at_level("ERROR"),
    ):
        result = await call_codex("prompt", "gpt-5")
    assert result == "the answer"
    assert f"cursor cleanup failed for {calls[0][1]['cwd']}" in caplog.messages
