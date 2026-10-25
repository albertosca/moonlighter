import pytest
from moonlighter.core.config import ConfigError, llm_backend, load_config, validate_config

CODEX_MODELS = {"llm_model": "gpt-6-luna", "eval_model": "gpt-6-luna"}


def test_llm_backend_accepts_codex():
    assert llm_backend({"llm_backend": "codex"}) == "codex"


def test_unknown_backend_message_lists_codex():
    with pytest.raises(ConfigError, match=r"cli, api, cursor, codex"):
        llm_backend({"llm_backend": "gemini"})


def test_validate_config_accepts_codex_with_non_claude_models():
    validate_config({"llm_backend": "codex", **CODEX_MODELS})


@pytest.mark.parametrize("key", ["llm_model", "eval_model"])
@pytest.mark.parametrize("bad", ["claude-sonnet-4-6", "Claude-Haiku", ""])
def test_validate_config_rejects_a_claude_or_empty_model_for_codex(key, bad):
    """The Codex CLI cannot run Anthropic ids, and the shipped defaults are Claude
    ids: without this the failure surfaces mid-scan, one call at a time."""
    config = {"llm_backend": "codex", **CODEX_MODELS, key: bad}
    with pytest.raises(ConfigError, match=key):
        validate_config(config)


def test_validate_config_codex_with_the_default_models_names_the_fix():
    with pytest.raises(ConfigError, match="llm_model"):
        validate_config({"llm_backend": "codex"})


def test_validate_config_leaves_claude_models_alone_for_other_backends():
    validate_config({"llm_backend": "cli", "llm_model": "claude-sonnet-4-6"})


def test_load_config_codex_eval_model_falls_back_to_llm_model(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("llm_backend: codex\nllm_model: gpt-6-luna\n")
    config = load_config(tmp_path / "config.yaml")
    assert config["eval_model"] == "gpt-6-luna"
    validate_config(config)


def test_load_config_codex_keeps_an_explicit_eval_model(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "llm_backend: codex\nllm_model: gpt-6-luna\neval_model: gpt-6-mini\n"
    )
    assert load_config(tmp_path / "config.yaml")["eval_model"] == "gpt-6-mini"


def test_load_config_leaves_the_eval_model_default_for_other_backends(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("llm_backend: cli\nllm_model: claude-opus-4-1\n")
    assert load_config(tmp_path / "config.yaml")["eval_model"].startswith("claude")


def test_codex_backend_never_loads_the_anthropic_key(tmp_path, monkeypatch):
    from moonlighter.core import config as config_module

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    key_file = tmp_path / "api.env"
    key_file.write_text("ANTHROPIC_API_KEY=sk-from-file\n")
    monkeypatch.setattr(config_module, "anthropic_api_env_file", lambda: key_file)
    (tmp_path / "config.yaml").write_text("llm_backend: codex\nllm_model: gpt-6-luna\n")
    load_config(tmp_path / "config.yaml")
    import os

    assert "ANTHROPIC_API_KEY" not in os.environ
