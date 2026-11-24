"""A call that works: what it starts, what it sends, and what it leaves behind."""

import json
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from moonlighter.core.llm.opencode import call_opencode
from moonlighter.core.llm.opencode_profile import locked_config, opencode_run_argv
from moonlighter.core.metrics import operation_metrics
from tests.core.llm.opencode.events import SESSION_ID, TEXT_RUN
from tests.core.llm.opencode.fake_opencode import FakeOpencode

SPAWN = "moonlighter.core.llm.isolation.asyncio.create_subprocess_exec"


@pytest.fixture
def fake():
    return FakeOpencode(TEXT_RUN)


async def _call(fake: FakeOpencode, prompt: str = "Reply PONG.", **keywords) -> str:
    with patch(SPAWN, fake.create):
        return await call_opencode(prompt, "fake/echo", **keywords)


async def test_the_answer_is_the_text_the_model_printed(fake):
    assert await _call(fake) == "PONG"


async def test_the_run_argv_is_the_locked_one(fake):
    await _call(fake)
    assert list(fake.run.argv) == opencode_run_argv("/opt/bin/opencode", "fake/echo")


async def test_the_prompt_goes_over_stdin_and_never_into_argv(fake):
    await _call(fake, "a secret résumé line")
    assert fake.run.stdin == "a secret résumé line".encode()
    assert not any("secret" in argument for launch in fake.launches for argument in launch.argv)


async def test_a_cache_prefix_comes_first_on_stdin(fake):
    await _call(fake, "the question", cache_prefix="the context")
    assert fake.run.stdin == b"the context\n\nthe question"


async def test_the_call_runs_in_a_private_workdir_with_the_locked_config(fake, tmp_path):
    seen: dict[str, object] = {}

    async def create(*argv, **options):
        if argv[1] == "run":
            workdir = Path(options["cwd"])
            seen["mode"] = stat.S_IMODE(workdir.stat().st_mode)  # noqa: ASYNC240 - a test inspecting the workdir; nothing else runs on the loop
            seen["config"] = json.loads((workdir / "opencode.json").read_text())
            seen["config_directory"] = Path(options["env"]["OPENCODE_CONFIG_DIR"])
        return await fake.create(*argv, **options)

    with patch(SPAWN, create):
        await call_opencode("Reply PONG.", "fake/echo")
    workdir = Path(fake.run.options["cwd"])
    assert workdir.parent == tmp_path / "home"
    assert seen["mode"] == 0o700
    assert seen["config"] == locked_config()
    assert seen["config_directory"] == workdir / "config"
    assert not workdir.exists()  # noqa: ASYNC240 - a test inspecting the workdir; nothing else runs on the loop


async def test_an_inherited_config_pointer_never_reaches_the_child(fake, monkeypatch):
    monkeypatch.setenv("OPENCODE_CONFIG", "/home/me/opencode.json")
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", "/home/me/.config/opencode")
    await _call(fake)
    environment = fake.run.options["env"]
    assert "OPENCODE_CONFIG" not in environment
    assert environment["OPENCODE_CONFIG_DIR"] != "/home/me/.config/opencode"


async def test_the_run_gets_its_own_process_group(fake):
    await _call(fake)
    assert fake.run.options["start_new_session"] is True


async def test_the_session_is_deleted_afterwards_from_the_same_workdir(fake):
    await _call(fake)
    (delete,) = fake.deletes
    assert list(delete.argv) == [
        "/opt/bin/opencode",
        "session",
        "delete",
        "--standalone",
        SESSION_ID,
    ]
    assert delete.options["cwd"] == fake.run.options["cwd"]
    assert delete.options["env"] == fake.run.options["env"]


async def test_a_call_records_one_call(fake):
    with operation_metrics("pin") as metrics:
        await _call(fake)
    assert metrics.calls == 1
