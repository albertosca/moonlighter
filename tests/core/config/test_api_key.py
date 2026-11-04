import os
from pathlib import Path

import pytest
from moonlighter.core.config import api_key
from moonlighter.core.config.api_key import anthropic_api_env_file
from moonlighter.core.config.loading import load_config


@pytest.fixture
def provider_file(tmp_path, monkeypatch):
    key_file = tmp_path / "api.env"
    monkeypatch.setattr(api_key, "anthropic_api_env_file", lambda: key_file)
    # setenv first so teardown restores the variable even when load_config sets it.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    return key_file


def _config_with_backend(tmp_path, backend: str) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f"llm_backend: {backend}\n")
    return config_path


def test_api_backend_loads_the_key_from_the_provider_file(tmp_path, provider_file):
    provider_file.write_text("# comment\nOTHER_NAME=ignored\nANTHROPIC_API_KEY=sk-from-file\n")
    load_config(_config_with_backend(tmp_path, "api"))
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-from-file"
    assert "OTHER_NAME" not in os.environ


def test_a_key_already_in_the_environment_wins_over_the_file(tmp_path, provider_file, monkeypatch):
    provider_file.write_text("ANTHROPIC_API_KEY=sk-from-file\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    load_config(_config_with_backend(tmp_path, "api"))
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-from-env"


def test_cli_backend_never_loads_the_key(tmp_path, provider_file):
    provider_file.write_text("ANTHROPIC_API_KEY=sk-from-file\n")
    load_config(_config_with_backend(tmp_path, "cli"))
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_cursor_backend_never_loads_the_key(tmp_path, provider_file):
    provider_file.write_text("ANTHROPIC_API_KEY=sk-from-file\n")
    load_config(_config_with_backend(tmp_path, "cursor"))
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_codex_backend_never_loads_the_anthropic_key(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    key_file = tmp_path / "api.env"
    key_file.write_text("ANTHROPIC_API_KEY=sk-from-file\n")
    monkeypatch.setattr(api_key, "anthropic_api_env_file", lambda: key_file)
    (tmp_path / "config.yaml").write_text("llm_backend: codex\nllm_model: gpt-6-luna\n")
    load_config(tmp_path / "config.yaml")
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_a_missing_or_unreadable_file_is_not_an_error(tmp_path, provider_file):
    load_config(_config_with_backend(tmp_path, "api"))  # file absent
    provider_file.mkdir()  # a directory where the file should be
    load_config(_config_with_backend(tmp_path, "api"))
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_a_non_utf8_file_is_not_an_error(tmp_path, provider_file):
    provider_file.write_bytes(b"ANTHROPIC_API_KEY=\xff\xfe\n")
    load_config(_config_with_backend(tmp_path, "api"))
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_a_file_without_a_usable_key_line_leaves_the_key_unset(tmp_path, provider_file):
    provider_file.write_text("OTHER_NAME=value\nANTHROPIC_API_KEY=\n")
    load_config(_config_with_backend(tmp_path, "api"))
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_the_provider_file_lives_under_home(tmp_path, monkeypatch):
    # Imported at collection time, so this is the real function, not the
    # autouse fixture's stand-in.
    monkeypatch.setenv("HOME", str(tmp_path))
    assert anthropic_api_env_file() == tmp_path / ".config" / "anthropic" / "api.env"
