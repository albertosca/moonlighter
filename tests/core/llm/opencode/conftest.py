"""The `opencode` backend: `opencode run` under a locked config, one call per prompt."""

import pytest


@pytest.fixture(autouse=True)
def _opencode_on_path(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "moonlighter.core.llm.opencode.shutil.which",
        lambda name: "/opt/bin/opencode" if name == "opencode" else None,
    )
