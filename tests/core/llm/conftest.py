from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def _no_real_cursor_projects(monkeypatch):
    """Transcript cleanup must not walk the developer's ~/.cursor/projects."""
    monkeypatch.setattr(
        "moonlighter.core.llm.cursor_projects._cursor_projects_root",
        lambda: Path("/no/such/cursor/projects"),
    )


@pytest.fixture
def _fake_claude_on_path():
    """Tests must not depend on whether `claude` happens to be installed on the
    machine running them (it never is in CI). Fix `shutil.which` to a stable
    fake path for every test that requests this fixture; tests that need a different
    resolution (found elsewhere, or absent) patch it explicitly, which
    overrides this outer patch for their duration.
    """
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        yield
