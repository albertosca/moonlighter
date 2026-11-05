"""The `codex` backend: the Codex CLI on the user's ChatGPT login.

Idea and first implementation: JR2PROJETOS (issue 121). The permission profile is
what the 2026-10-25 canary showed is needed: `--sandbox read-only` blocks writes
and the network but still reads `~/.codex/auth.json` and `~/.ssh`.
"""

import pytest
from moonlighter.core.llm import codex, codex_profile


@pytest.fixture(autouse=True)
def _codex_on_path(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        codex.shutil, "which", lambda name: "/opt/bin/codex" if name == "codex" else None
    )
    monkeypatch.setattr(codex_profile.os.path, "realpath", str)
