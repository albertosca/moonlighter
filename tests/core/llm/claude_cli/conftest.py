import pytest


@pytest.fixture(autouse=True)
def _claude_on_path(_fake_claude_on_path):
    """Every test here resolves `claude` to the stable fake path, never the machine's own."""
