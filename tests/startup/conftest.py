from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _fake_claude_on_path():
    """`claude` is installed on the dev machine and never in CI. Without a fixed
    resolution the cli-backend check would make this module pass locally and
    fail in CI. Tests that need it absent patch `which` themselves."""
    with patch("moonlighter.startup.shutil.which", return_value="/usr/local/bin/claude"):
        yield
