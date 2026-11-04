from pathlib import Path

import pytest
import yaml
from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.loading import load_config
from moonlighter.core.config.validation import validate_config


def _valid_config():
    # A fully-populated, valid config (defaults + the optional blocks).
    return load_config()  # DEFAULTS-merged, no user file in test env → valid baseline


class TestValidateConfig:
    def test_valid_config_passes(self):
        validate_config(_valid_config())  # must not raise

    def test_wrong_type_scalar_raises_naming_key(self):
        config = _valid_config()
        config["scan_concurrency"] = "five"
        with pytest.raises(ConfigError, match="scan_concurrency"):
            validate_config(config)

    def test_bool_rejected_where_int_required(self):
        config = _valid_config()
        config["slow_mo_ms"] = True
        with pytest.raises(ConfigError, match="slow_mo_ms"):
            validate_config(config)

    def test_unknown_top_level_key_raises(self):
        config = _valid_config()
        config["scan_concurrancy"] = 5  # typo
        with pytest.raises(ConfigError, match="scan_concurrancy"):
            validate_config(config)

    def test_unknown_email_subkey_raises(self):
        config = _valid_config()
        config["email"] = {"address": "a@b.com", "unexpected": 1}
        with pytest.raises(ConfigError, match=r"email.unexpected"):
            validate_config(config)

    def test_title_blocklist_must_be_list(self):
        config = _valid_config()
        config["title_blocklist"] = "senior"
        with pytest.raises(ConfigError, match="title_blocklist"):
            validate_config(config)

    def test_cv_must_be_dict(self):
        config = _valid_config()
        config["cv"] = "cv.pdf"
        with pytest.raises(ConfigError, match="cv"):
            validate_config(config)

    def test_score_threshold_accepts_int_and_float(self):
        config = _valid_config()
        config["score_threshold"] = 7
        validate_config(config)
        config["score_threshold"] = 7.5
        validate_config(config)

    def test_omitted_optional_block_passes(self):
        config = _valid_config()
        config.pop("email", None)  # email is optional
        validate_config(config)

    def test_zero_lookback_days_rejected(self):
        """Gmail's newer_than:0d matches zero messages (verified live), so a
        lookback_days of 0 silently disables the sync forever — reading exactly
        like an empty mailbox instead of the config mistake it is."""
        config = _valid_config()
        config["email"] = {"lookback_days": 0}
        with pytest.raises(ConfigError, match="lookback_days"):
            validate_config(config)

    def test_negative_lookback_days_rejected(self):
        config = _valid_config()
        config["email"] = {"lookback_days": -1}
        with pytest.raises(ConfigError, match="lookback_days"):
            validate_config(config)

    def test_positive_lookback_days_accepted(self):
        config = _valid_config()
        config["email"] = {"lookback_days": 30}
        validate_config(config)  # must not raise

    def test_example_config_validates(self):
        example = Path(__file__).resolve().parents[3] / "config.example.yaml"
        user = yaml.safe_load(example.read_text()) or {}
        merged = {**DEFAULTS, "browser_session_dir": "x", "screenshots_dir": "y", **user}
        validate_config(merged)  # must not raise

    def test_validate_config_accepts_scan_gupy(self):
        """Regression: scan_gupy (Gupy's config gate) was never added to
        _CONFIG_SCHEMA, so setting it in config.yaml raised
        ConfigError: unknown config key 'scan_gupy'. Never triggered in
        practice because it was never set — caught while adding the 4 new
        remote-board flags to the same schema section."""
        validate_config({"scan_gupy": True})

    def test_validate_config_accepts_remote_board_flags(self):
        validate_config(
            {
                "scan_remoteok": True,
                "scan_remotive": False,
                "scan_wwr": True,
                "scan_hn_whoishiring": False,
            }
        )


class TestAnswerBankMaxAge:
    def test_null_disables_expiry_and_is_valid(self):
        validate_config({"answer_bank_max_age_days": None})

    def test_int_is_valid(self):
        validate_config({"answer_bank_max_age_days": 30})

    def test_string_is_rejected_naming_the_key(self):
        with pytest.raises(ConfigError, match="answer_bank_max_age_days"):
            validate_config({"answer_bank_max_age_days": "90"})


def test_validate_config_accepts_cursor_model():
    validate_config({"cursor_model": "gpt-5"})


def test_validate_config_rejects_a_non_string_cursor_model():
    with pytest.raises(ConfigError, match="cursor_model"):
        validate_config({"cursor_model": 1})


def test_cv_schema_accepts_tailored_cv_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "cv:\n"
        "  default: cv.pdf\n"
        "  pool: /somewhere/cv-pool.yaml\n"
        "  template_dir: /somewhere/templates\n"
        "  generated_dir: /somewhere/generated\n"
    )
    config = load_config()
    validate_config(config)
    assert config["cv"]["pool"] == "/somewhere/cv-pool.yaml"
    assert config["cv"]["template_dir"] == "/somewhere/templates"
    assert config["cv"]["generated_dir"] == "/somewhere/generated"


# llm_timeout_seconds: how long a `claude -p` call may run before it is killed.


def test_a_positive_timeout_is_accepted():
    config = load_config()
    config["llm_timeout_seconds"] = 300
    validate_config(config)


@pytest.mark.parametrize("value", [0, -5])
def test_a_non_positive_timeout_is_rejected(value):
    """Zero would kill every call before it answered — a config mistake that reads
    like the CLI being broken."""
    config = load_config()
    config["llm_timeout_seconds"] = value
    with pytest.raises(ConfigError, match="llm_timeout_seconds"):
        validate_config(config)


def test_a_non_numeric_timeout_is_rejected():
    config = load_config()
    config["llm_timeout_seconds"] = "three minutes"
    with pytest.raises(ConfigError, match="llm_timeout_seconds"):
        validate_config(config)


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"zzz": 1, "llm_timeout_seconds": 0}, "unknown config key 'zzz'"),
        (
            {"llm_timeout_seconds": 0, "zzz": 1},
            "config key 'llm_timeout_seconds' must be positive, got 0",
        ),
        ({"email": {"zzz": 1, "lookback_days": 0}}, "unknown config key 'email.zzz'"),
        (
            {"email": {"lookback_days": 0, "zzz": 1}},
            "config key 'email.lookback_days' must be positive, got 0",
        ),
        ({"cv": {"pool": 5, "zzz": 1}}, "config key 'cv.pool' must be str, got int"),
        ({"scan_concurrency": True}, "config key 'scan_concurrency' must be int, got bool"),
        ({"score_threshold": "high"}, "config key 'score_threshold' must be int, float, got str"),
    ],
)
def test_a_rejected_config_names_its_first_bad_key_in_these_exact_words(config, message):
    with pytest.raises(ConfigError) as raised:
        validate_config(config)
    assert str(raised.value) == message
