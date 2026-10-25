import pytest
import yaml
from moonlighter.core.config import ConfigError, load_config, validate_config
from moonlighter.init import run_init

ANSWERS = {"browser_path": "/x", "citizenship_country": "Brazil", "llm_backend": "codex"}


def test_run_init_writes_codex_models_that_load_back(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    path = run_init(tmp_path, {**ANSWERS, "llm_model": "gpt-6-luna"})
    written = yaml.safe_load(path.read_text())
    assert written["llm_model"] == "gpt-6-luna"
    assert written["eval_model"] == "gpt-6-luna"
    validate_config(load_config(path))


def test_run_init_keeps_a_separate_codex_eval_model(tmp_path):
    path = run_init(tmp_path, {**ANSWERS, "llm_model": "gpt-6-luna", "eval_model": "gpt-6-mini"})
    assert yaml.safe_load(path.read_text())["eval_model"] == "gpt-6-mini"


@pytest.mark.parametrize("model", ["", "claude-sonnet-4-6"])
def test_run_init_refuses_codex_without_a_usable_model(tmp_path, model):
    """The wizard must not write a config that the next boot refuses to load."""
    with pytest.raises(ConfigError, match="llm_model"):
        run_init(tmp_path, {**ANSWERS, "llm_model": model})
    assert not (tmp_path / "config.yaml").exists()


def test_run_init_does_not_write_models_for_other_backends(tmp_path):
    path = run_init(tmp_path, {**ANSWERS, "llm_backend": "cli"})
    written = yaml.safe_load(path.read_text())
    assert "llm_model" not in written
    assert "eval_model" not in written
