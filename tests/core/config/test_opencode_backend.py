"""`llm_backend: opencode`: accepted, and only with provider/model models."""

import pytest

from moonlighter.core.config.backends import llm_backend
from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.validation import validate_config

OPENCODE_MODELS = {
    "llm_model": "anthropic/claude-sonnet-5-5",
    "eval_model": "anthropic/claude-sonnet-5-5",
}


def test_opencode_is_a_backend():
    assert llm_backend({"llm_backend": "opencode"}) == "opencode"


def test_validate_config_accepts_opencode_with_provider_models():
    validate_config({"llm_backend": "opencode", **OPENCODE_MODELS})


@pytest.mark.parametrize("key", ["llm_model", "eval_model"])
@pytest.mark.parametrize("bad", ["", "claude-sonnet-4-6", "/x", "x/"])
def test_validate_config_refuses_a_model_without_a_provider(key, bad):
    """`opencode run -m` takes provider/model; anything else fails on every call."""
    config = {"llm_backend": "opencode", **OPENCODE_MODELS, key: bad}
    with pytest.raises(ConfigError, match=key):
        validate_config(config)


def test_the_refusal_reads_word_for_word():
    config = {"llm_backend": "opencode", **OPENCODE_MODELS, "llm_model": "claude-sonnet-4-6"}
    with pytest.raises(ConfigError) as raised:
        validate_config(config)
    assert str(raised.value) == (
        "config key 'llm_model' must name an opencode model as provider/model (for example "
        "'anthropic/claude-sonnet-5-5'; `opencode models` lists them) when llm_backend is "
        "'opencode', got 'claude-sonnet-4-6'"
    )


def test_the_shipped_default_models_are_refused_for_opencode():
    with pytest.raises(ConfigError, match="llm_model"):
        validate_config({"llm_backend": "opencode"})


def test_a_bad_key_is_reported_before_the_opencode_models():
    with pytest.raises(ConfigError) as raised:
        validate_config({"llm_backend": "opencode", "llm_model": "x", "zzz": 1})
    assert str(raised.value) == "unknown config key 'zzz'"


def test_other_backends_leave_provider_models_alone():
    validate_config({"llm_backend": "cli", "llm_model": "claude-sonnet-4-6"})
