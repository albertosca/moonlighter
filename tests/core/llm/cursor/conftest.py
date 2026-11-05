import pytest


@pytest.fixture(autouse=True)
def _cursor_guards(_no_real_cursor_projects, _fake_claude_on_path):
    """Every test here keeps transcript cleanup away from the real ~/.cursor/projects
    and resolves its binary to a stable fake path, never the machine's own.
    """
