"""A prompt that cannot be encoded fails before any CLI process or private workdir exists."""

from unittest.mock import AsyncMock, patch

import pytest

from moonlighter.core.llm import claude_cli, codex, cursor, opencode

UNENCODABLE_PROMPT = "a lone surrogate \ud800"


@pytest.mark.parametrize(
    "backend",
    [
        (claude_cli, claude_cli.call_cli, "gpt-5"),
        (cursor, cursor.call_cursor, "gpt-5"),
        (codex, codex.call_codex, "gpt-5"),
        (opencode, opencode.call_opencode, "fake/echo"),
    ],
    ids=["claude", "cursor", "codex", "opencode"],
)
async def test_an_unencodable_prompt_spawns_nothing_and_leaves_no_workdir(
    backend, monkeypatch, tmp_path
):
    module, call, model = backend
    home = tmp_path / "home"
    monkeypatch.setenv("MOONLIGHTER_HOME", str(home))
    spawn = AsyncMock()
    with (
        patch.object(module.shutil, "which", return_value="/opt/bin/cli"),
        patch("moonlighter.core.llm.isolation.asyncio.create_subprocess_exec", spawn),
        pytest.raises(UnicodeEncodeError),
    ):
        await call(UNENCODABLE_PROMPT, model)
    spawn.assert_not_called()
    assert not home.exists() or list(home.iterdir()) == []
