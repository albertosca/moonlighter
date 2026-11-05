"""The suite never reads or writes the developer's real moonlighter data."""

import os
import tempfile
from pathlib import Path

from moonlighter.core.config import api_key, paths


def test_moonlighter_home_is_a_session_temp_directory():
    home = Path(os.environ["MOONLIGHTER_HOME"])

    assert home.name.startswith("moonlighter-test-home-")
    assert home.resolve().parent == Path(tempfile.gettempdir()).resolve()
    assert home.is_dir()
    assert paths.moonlighter_home() == home


def test_the_anthropic_api_env_file_is_never_the_real_one():
    credentials_file = api_key.anthropic_api_env_file()

    assert not credentials_file.exists()
    assert credentials_file.parent.name.startswith("no-api-env")
