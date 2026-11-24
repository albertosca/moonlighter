from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _startup_finds_claude():
    """`claude` is installed on the dev machine and never in CI. Without a fixed
    resolution the cli-backend check would make this module pass locally and
    fail in CI. Tests that need it absent patch `which` themselves.
    """
    with patch("moonlighter.startup.shutil.which", return_value="/usr/local/bin/claude"):
        yield


@pytest.fixture(autouse=True)
def _startup_finds_no_opencode():
    """`opencode` may be on the dev machine and is never in CI: resolve it the CI way.
    Tests that need it present patch `opencode_executable` themselves.
    """
    with patch("moonlighter.startup.opencode_executable", return_value=None):
        yield
