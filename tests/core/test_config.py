from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from moonlighter.core.config import (
    ConfigError,
    load_company_list,
    load_config,
    load_profile,
    moonlighter_home,
    validate_config,
)


def test_load_config_defaults(tmp_path):
    # No config.yaml → all defaults
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    assert config["score_threshold"] == 6.5
    assert config["slow_mo_ms"] == 300
    assert config["llm_model"] == "claude-sonnet-4-6"


def test_load_config_overrides(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("score_threshold: 7.5\nllm_model: claude-opus-4-7\n")
    config = load_config(config_path=str(cfg_file))
    assert config["score_threshold"] == 7.5
    assert config["llm_model"] == "claude-opus-4-7"
    assert config["slow_mo_ms"] == 300  # default still present


def test_load_profile(tmp_path):
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text("""
skills:
  - name: Elixir/Phoenix
    years: 8
    level: expert
criteria:
  hard_filters:
    - "descarta se exigir .NET"
""")
    profile = load_profile(profile_path=str(profile_file))
    assert profile["skills"][0]["name"] == "Elixir/Phoenix"
    assert len(profile["criteria"]["hard_filters"]) == 1


def test_load_company_list(tmp_path):
    company_file = tmp_path / "company_list.yaml"
    company_file.write_text("""
greenhouse:
  - stripe
  - linear
lever:
  - gitlab
""")
    company_list = load_company_list(path=str(company_file))
    assert company_list["greenhouse"] == ["stripe", "linear"]
    assert company_list["lever"] == ["gitlab"]


def test_load_company_list_nonexistent():
    # If file doesn't exist, return empty dict
    company_list = load_company_list(path="/nonexistent/path.yaml")
    assert company_list == {}


# --- load_config: path expansion ---


def test_load_config_path_keys_expanded(tmp_path):
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    assert "~" not in config["browser_session_dir"]
    assert "~" not in config["screenshots_dir"]


def test_load_config_empty_yaml_uses_defaults(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("")
    config = load_config(config_path=str(cfg_file))
    assert config["score_threshold"] == 6.5
    assert config["slow_mo_ms"] == 300
    assert config["llm_model"] == "claude-sonnet-4-6"


def test_load_config_partial_override(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("score_threshold: 8.0\n")
    config = load_config(config_path=str(cfg_file))
    assert config["score_threshold"] == 8.0
    assert config["slow_mo_ms"] == 300
    assert config["llm_model"] == "claude-sonnet-4-6"


def test_load_config_all_path_keys_no_tilde(tmp_path):
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    for key in ("browser_session_dir", "screenshots_dir"):
        assert "~" not in config[key], f"{key} still contains '~'"


def test_browser_executable_prefers_browser_path():
    from moonlighter.core.config import browser_executable

    assert browser_executable({"browser_path": "/usr/bin/chrome"}) == "/usr/bin/chrome"


def test_browser_executable_falls_back_to_legacy_brave_path():
    from moonlighter.core.config import browser_executable

    assert (
        browser_executable({"browser_path": "", "brave_path": "/legacy/brave"}) == "/legacy/brave"
    )
    assert browser_executable({"brave_path": "/legacy/brave"}) == "/legacy/brave"
    assert browser_executable({}) == ""


# --- load_profile ---


def test_load_profile_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_profile(profile_path="/nonexistent/profile.yaml")


def test_load_profile_empty_yaml_returns_empty_dict(tmp_path):
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text("")
    profile = load_profile(profile_path=str(profile_file))
    assert profile == {}


def test_load_profile_full_structure(tmp_path):
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text("""
skills:
  - name: Elixir/Phoenix
    years: 8
experience:
  - company: Acme
    role: Senior Dev
preferences:
  remote: true
criteria:
  hard_filters:
    - "descarta se exigir .NET"
""")
    profile = load_profile(profile_path=str(profile_file))
    for key in ("skills", "experience", "preferences", "criteria"):
        assert key in profile, f"key '{key}' missing from profile"


# --- load_company_list ---


def test_load_company_list_empty_yaml(tmp_path):
    company_file = tmp_path / "company_list.yaml"
    company_file.write_text("")
    result = load_company_list(path=str(company_file))
    assert result == {}


def test_load_company_list_multiple_sources(tmp_path):
    company_file = tmp_path / "company_list.yaml"
    company_file.write_text("""
greenhouse:
  - stripe
lever:
  - gitlab
ashby:
  - notion
""")
    result = load_company_list(path=str(company_file))
    for key in ("greenhouse", "lever", "ashby"):
        assert key in result, f"key '{key}' missing from company list"


# --- moonlighter_home ---


def test_moonlighter_home_default(monkeypatch):
    monkeypatch.delenv("MOONLIGHTER_HOME", raising=False)
    home = moonlighter_home()
    assert home == (Path.home() / ".moonlighter")


def test_moonlighter_home_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    assert moonlighter_home() == tmp_path


# --- load_config default path ---


def test_load_config_default_path_uses_moonlighter_home(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    config = load_config()  # sem config.yaml → usa defaults
    assert config["score_threshold"] == 6.5


# --- learned blocklist merge (branches) ---


def test_load_config_no_learned_blocklist(tmp_path, monkeypatch):
    """No blocklist_learned.yaml → config proceeds without merging."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    assert "title_blocklist" in config


def test_load_config_learned_blocklist_empty(tmp_path, monkeypatch):
    """blocklist_learned.yaml exists but has no patterns → does not change anything."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    learned = tmp_path / "blocklist_learned.yaml"
    learned.write_text("title_blocklist: []\n")
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    assert config.get("title_blocklist", []) == []


def test_load_config_learned_blocklist_merges(tmp_path, monkeypatch):
    """Learned patterns are merged after the manual ones, without duplicating."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    learned = tmp_path / "blocklist_learned.yaml"
    learned.write_text("title_blocklist:\n  - recruiter\n  - intern\n")
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    assert "recruiter" in config["title_blocklist"]
    assert "intern" in config["title_blocklist"]


# --- load_company_list: value formats ---


def test_load_company_list_mixed_value_shapes(tmp_path):
    """A phase-dict with a non-list value is ignored; a scalar value becomes [] (125->124, 129)."""
    company_file = tmp_path / "company_list.yaml"
    company_file.write_text(
        "greenhouse:\n"
        "  phase1:\n"
        "    - stripe\n"
        "  phase_bad: not_a_list\n"
        "lever: 42\n"  # valor escalar (nem lista nem dict)
    )
    result = load_company_list(path=str(company_file))  # phase=None → concatena
    assert result["greenhouse"] == ["stripe"]
    assert result["lever"] == []


def test_load_company_list_with_phase_filter(tmp_path):
    """When phase is specified, returns only that phase's slugs."""
    company_file = tmp_path / "company_list.yaml"
    company_file.write_text("greenhouse:\n  phase1:\n    - stripe\n  phase2:\n    - linear\n")
    result = load_company_list(path=str(company_file), phase="phase1")
    assert result["greenhouse"] == ["stripe"]


# --- scan_concurrency ---


def test_scan_concurrency_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    from moonlighter.core.config import load_config

    assert load_config()["scan_concurrency"] == 5


def test_scan_concurrency_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("scan_concurrency: 3\n")
    from moonlighter.core.config import load_config

    assert load_config()["scan_concurrency"] == 3


def test_scan_batch_size_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    from moonlighter.core.config import load_config

    assert load_config()["scan_batch_size"] == 5


# --- harden_permissions (S-07) ---


def test_harden_permissions_chmods_files_0600(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "moonlighter.db").write_text("x")
    (tmp_path / "moonlighter.db").chmod(0o644)
    from moonlighter.core.config import harden_permissions

    warnings = harden_permissions()
    assert warnings == []
    assert oct((tmp_path / "moonlighter.db").stat().st_mode)[-3:] == "600"


def test_harden_permissions_chmods_dirs_0700(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "browser-session").mkdir()
    (tmp_path / "browser-session").chmod(0o755)
    from moonlighter.core.config import harden_permissions

    harden_permissions()
    assert oct((tmp_path / "browser-session").stat().st_mode)[-3:] == "700"


def test_harden_permissions_skips_missing_files(tmp_path, monkeypatch):
    """No real files in MOONLIGHTER_HOME → nothing to fix, no error."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    from moonlighter.core.config import harden_permissions

    assert harden_permissions() == []


def _valid_config():
    # A fully-populated, valid config (defaults + the optional blocks).
    return load_config()  # DEFAULTS-merged, no user file in test env → valid baseline


class TestValidateConfig:
    def test_valid_config_passes(self):
        validate_config(_valid_config())  # must not raise

    def test_wrong_type_scalar_raises_naming_key(self):
        cfg = _valid_config()
        cfg["scan_concurrency"] = "five"
        with pytest.raises(ConfigError, match="scan_concurrency"):
            validate_config(cfg)

    def test_bool_rejected_where_int_required(self):
        cfg = _valid_config()
        cfg["slow_mo_ms"] = True
        with pytest.raises(ConfigError, match="slow_mo_ms"):
            validate_config(cfg)

    def test_unknown_top_level_key_raises(self):
        cfg = _valid_config()
        cfg["scan_concurrancy"] = 5  # typo
        with pytest.raises(ConfigError, match="scan_concurrancy"):
            validate_config(cfg)

    def test_unknown_email_subkey_raises(self):
        cfg = _valid_config()
        cfg["email"] = {"address": "a@b.com", "unexpected": 1}
        with pytest.raises(ConfigError, match=r"email.unexpected"):
            validate_config(cfg)

    def test_title_blocklist_must_be_list(self):
        cfg = _valid_config()
        cfg["title_blocklist"] = "senior"
        with pytest.raises(ConfigError, match="title_blocklist"):
            validate_config(cfg)

    def test_cv_must_be_dict(self):
        cfg = _valid_config()
        cfg["cv"] = "cv.pdf"
        with pytest.raises(ConfigError, match="cv"):
            validate_config(cfg)

    def test_score_threshold_accepts_int_and_float(self):
        cfg = _valid_config()
        cfg["score_threshold"] = 7
        validate_config(cfg)
        cfg["score_threshold"] = 7.5
        validate_config(cfg)

    def test_omitted_optional_block_passes(self):
        cfg = _valid_config()
        cfg.pop("email", None)  # email is optional
        validate_config(cfg)

    def test_example_config_validates(self):
        from moonlighter.core.config import DEFAULTS

        example = Path(__file__).resolve().parents[2] / "config.example.yaml"
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


def test_harden_permissions_warns_on_chmod_failure_without_raising(tmp_path, monkeypatch):
    """A permission error must never crash the server's startup — it becomes
    a warning, not an exception."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "profile.yaml").write_text("x")
    (tmp_path / "browser-session").mkdir()
    from moonlighter.core import config as config_mod

    with patch.object(config_mod.Path, "chmod", side_effect=OSError("read-only fs")):
        warnings = config_mod.harden_permissions()

    assert len(warnings) >= 2
    assert any("profile.yaml" in w or "permiss" in w.lower() for w in warnings)
    assert any("browser-session" in w or "permiss" in w.lower() for w in warnings)


# ── llm_backend ───────────────────────────────────────────────────────────────


def test_llm_backend_defaults_to_cli_when_omitted():
    """The subscription path is the default: `uvx moonlighter` users generally
    have Claude Code and no API key."""
    from moonlighter.core.config import llm_backend

    assert llm_backend({}) == "cli"


def test_llm_backend_returns_the_configured_value():
    from moonlighter.core.config import llm_backend

    assert llm_backend({"llm_backend": "api"}) == "api"
    assert llm_backend({"llm_backend": "cli"}) == "cli"


@pytest.mark.parametrize("bad", ["CLI", "Api", "clii", "subscription", ""])
def test_llm_backend_rejects_anything_else_naming_the_valid_values(bad):
    """These all used to select the api backend in silence -- 'CLI' being the
    most plausible typo, and the most expensive, since it demands an API key."""
    from moonlighter.core.config import llm_backend

    with pytest.raises(ConfigError, match="cli, api"):
        llm_backend({"llm_backend": bad})


def test_validate_config_rejects_an_unknown_llm_backend():
    with pytest.raises(ConfigError, match="cli, api"):
        validate_config({"llm_backend": "CLI"})


def test_validate_config_accepts_both_backends():
    validate_config({"llm_backend": "cli"})
    validate_config({"llm_backend": "api"})


def test_load_config_fills_llm_backend_from_defaults(tmp_path, monkeypatch):
    """The default has to arrive through DEFAULTS, not through a `.get()`
    fallback at each call site -- that divergence is what made the wizard, the
    README, and the factory disagree about which backend an omitted key means."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("score_threshold: 7.0\n")

    assert load_config(tmp_path / "config.yaml")["llm_backend"] == "cli"
