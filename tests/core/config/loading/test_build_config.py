"""build_config: the defaults merged under a user mapping, validated, sharing nothing with DEFAULTS."""

import pytest

from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.loading import build_config, load_config


def test_a_nested_override_keeps_the_blocks_other_defaults():
    config = build_config({"email": {"address": "jane@example.com"}})
    assert config["email"]["address"] == "jane@example.com"
    assert config["email"]["token_path"] == DEFAULTS["email"]["token_path"]


def test_codex_without_an_eval_model_evaluates_with_llm_model():
    config = build_config({"llm_backend": "codex", "llm_model": "gpt-6-luna"})
    assert config["eval_model"] == "gpt-6-luna"


def test_codex_keeps_an_explicit_eval_model():
    config = build_config(
        {"llm_backend": "codex", "llm_model": "gpt-6-luna", "eval_model": "gpt-6-mini"}
    )
    assert config["eval_model"] == "gpt-6-mini"


def test_an_invalid_value_raises_config_error_naming_the_key():
    with pytest.raises(ConfigError, match="scan_concurrency"):
        build_config({"scan_concurrency": "five"})


def test_load_config_validates_what_it_loads(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("scan_concurrency: five\n")
    with pytest.raises(ConfigError, match="scan_concurrency"):
        load_config(config_path=config_file)


def test_a_mutated_block_does_not_reach_the_next_load(tmp_path):
    missing = tmp_path / "nonexistent.yaml"
    load_config(config_path=missing)["email"]["interview_stages"] = ["learned"]
    assert "interview_stages" not in load_config(config_path=missing)["email"]
    assert "interview_stages" not in DEFAULTS["email"]


def test_a_built_config_shares_no_block_with_the_defaults():
    config = build_config({})
    assert config["cv"]["by_company"] is not DEFAULTS["cv"]["by_company"]
    assert config["email"] is not DEFAULTS["email"]


def test_a_built_config_shares_no_block_with_the_overrides():
    overrides = {"cv": {"by_company": {"acme": "acme.pdf"}}, "title_blocklist": ["intern"]}
    config = build_config(overrides)
    config["cv"]["by_company"]["globex"] = "globex.pdf"
    config["title_blocklist"].append("senior")
    assert overrides == {"cv": {"by_company": {"acme": "acme.pdf"}}, "title_blocklist": ["intern"]}
