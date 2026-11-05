from moonlighter.core.config.loading import load_config
from moonlighter.core.config.validation import validate_config


def test_load_config_defaults(tmp_path):
    # No config.yaml → all defaults
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    assert config["score_threshold"] == 6.5
    assert config["slow_mo_ms"] == 300
    assert config["llm_model"] == "claude-sonnet-4-6"


def test_load_config_overrides(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("score_threshold: 7.5\nllm_model: claude-opus-4-7\n")
    config = load_config(config_path=str(config_file))
    assert config["score_threshold"] == 7.5
    assert config["llm_model"] == "claude-opus-4-7"
    assert config["slow_mo_ms"] == 300  # default still present


def test_load_config_empty_yaml_uses_defaults(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("")
    config = load_config(config_path=str(config_file))
    assert config["score_threshold"] == 6.5
    assert config["slow_mo_ms"] == 300
    assert config["llm_model"] == "claude-sonnet-4-6"


def test_load_config_partial_override(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("score_threshold: 8.0\n")
    config = load_config(config_path=str(config_file))
    assert config["score_threshold"] == 8.0
    assert config["slow_mo_ms"] == 300
    assert config["llm_model"] == "claude-sonnet-4-6"


def test_load_config_default_path_uses_moonlighter_home(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    config = load_config()  # sem config.yaml → usa defaults
    assert config["score_threshold"] == 6.5


# --- path expansion ---


def test_load_config_path_keys_expanded(tmp_path):
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    assert "~" not in config["browser_session_dir"]
    assert "~" not in config["screenshots_dir"]


def test_load_config_all_path_keys_no_tilde(tmp_path):
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    for key in ("browser_session_dir", "screenshots_dir"):
        assert "~" not in config[key], f"{key} still contains '~'"


# --- scan_concurrency ---


def test_scan_concurrency_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    assert load_config()["scan_concurrency"] == 5


def test_scan_concurrency_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("scan_concurrency: 3\n")
    assert load_config()["scan_concurrency"] == 3


def test_scan_batch_size_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    assert load_config()["scan_batch_size"] == 5


# --- llm backend keys ---


def test_load_config_keeps_cursor_model_and_does_not_invent_it(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("llm_backend: cursor\ncursor_model: gpt-5\n")
    assert load_config(tmp_path / "config.yaml")["cursor_model"] == "gpt-5"

    (tmp_path / "config.yaml").write_text("score_threshold: 7.0\n")
    assert "cursor_model" not in load_config(tmp_path / "config.yaml")


def test_load_config_fills_llm_backend_from_defaults(tmp_path, monkeypatch):
    """The default has to arrive through DEFAULTS, not through a `.get()`
    fallback at each call site -- that divergence is what made the wizard, the
    README, and the factory disagree about which backend an omitted key means.
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("score_threshold: 7.0\n")

    assert load_config(tmp_path / "config.yaml")["llm_backend"] == "cli"


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


# --- dict-valued defaults (email:) ---


def test_load_config_partial_email_block_keeps_sibling_defaults(tmp_path):
    # A user overriding ONE key inside a dict-valued default (email:) must not
    # lose the siblings -- the shallow update() replaced the whole dict, which
    # is the root cause behind the credentials guard firing on valid setups.
    config_file = tmp_path / "config.yaml"
    config_file.write_text("email:\n  credentials_path: my-creds.json\n")
    config = load_config(config_path=str(config_file))
    assert config["email"]["credentials_path"] == "my-creds.json"
    assert config["email"]["token_path"] == "gmail-token.json"


def test_load_config_full_email_block_still_overrides_both(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("email:\n  credentials_path: a.json\n  token_path: b.json\n")
    config = load_config(config_path=str(config_file))
    assert config["email"]["credentials_path"] == "a.json"
    assert config["email"]["token_path"] == "b.json"
