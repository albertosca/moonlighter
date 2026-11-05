import pytest
from moonlighter.core.config.backends import llm_backend
from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.validation import validate_config

CODEX_MODELS = {"llm_model": "gpt-6-luna", "eval_model": "gpt-6-luna"}


def test_llm_backend_defaults_to_cli_when_omitted():
    """The subscription path is the default: `uvx moonlighter` users generally
    have Claude Code and no API key.
    """
    assert llm_backend({}) == "cli"


def test_llm_backend_returns_the_configured_value():
    assert llm_backend({"llm_backend": "api"}) == "api"
    assert llm_backend({"llm_backend": "cli"}) == "cli"
    assert llm_backend({"llm_backend": "cursor"}) == "cursor"


@pytest.mark.parametrize("bad", ["CLI", "Api", "clii", "subscription", ""])
def test_llm_backend_rejects_anything_else_naming_the_valid_values(bad):
    """These all used to select the api backend in silence -- 'CLI' being the
    most plausible typo, and the most expensive, since it demands an API key.
    """
    with pytest.raises(ConfigError, match="cli, api, cursor"):
        llm_backend({"llm_backend": bad})


def test_validate_config_rejects_an_unknown_llm_backend():
    with pytest.raises(ConfigError, match="cli, api, cursor"):
        validate_config({"llm_backend": "CLI"})


def test_validate_config_accepts_known_backends():
    validate_config({"llm_backend": "cli"})
    validate_config({"llm_backend": "api"})
    validate_config({"llm_backend": "cursor"})


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
    ids: without this the failure surfaces mid-scan, one call at a time.
    """
    config = {"llm_backend": "codex", **CODEX_MODELS, key: bad}
    with pytest.raises(ConfigError, match=key):
        validate_config(config)


def test_validate_config_codex_with_the_default_models_names_the_fix():
    with pytest.raises(ConfigError, match="llm_model"):
        validate_config({"llm_backend": "codex"})


def test_validate_config_leaves_claude_models_alone_for_other_backends():
    validate_config({"llm_backend": "cli", "llm_model": "claude-sonnet-4-6"})


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"llm_backend": 5}, "config key 'llm_backend' must be str, got int"),
        (
            {"llm_backend": "CLI"},
            "config key 'llm_backend' must be one of cli, api, cursor, codex, got 'CLI'",
        ),
        (
            {"llm_backend": "codex", "llm_model": "claude-sonnet-4-6"},
            (
                "config key 'llm_model' must name a model the Codex CLI can run (for example "
                "'gpt-6-luna') when llm_backend is 'codex', got 'claude-sonnet-4-6'"
            ),
        ),
    ],
)
def test_a_rejected_backend_or_codex_model_reads_word_for_word(config, message):
    with pytest.raises(ConfigError) as raised:
        validate_config(config)
    assert str(raised.value) == message


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"llm_backend": "codex", "llm_model": "claude-x", "zzz": 1}, "unknown config key 'zzz'"),
        (
            {"llm_backend": "codex", "email": {"lookback_days": 0}},
            "config key 'email.lookback_days' must be positive, got 0",
        ),
    ],
)
def test_a_bad_key_is_reported_before_the_codex_models_are_checked(config, message):
    with pytest.raises(ConfigError) as raised:
        validate_config(config)
    assert str(raised.value) == message
