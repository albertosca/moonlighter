from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from gauntler.core.config import (
    ConfigError,
    gauntler_home,
    load_company_list,
    load_config,
    load_profile,
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
    from gauntler.core.config import browser_executable

    assert browser_executable({"browser_path": "/usr/bin/chrome"}) == "/usr/bin/chrome"


def test_browser_executable_falls_back_to_legacy_brave_path():
    from gauntler.core.config import browser_executable

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


# --- gauntler_home ---


def test_gauntler_home_default(monkeypatch):
    monkeypatch.delenv("GAUNTLER_HOME", raising=False)
    home = gauntler_home()
    assert home == (Path.home() / ".gauntler")


def test_gauntler_home_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    assert gauntler_home() == tmp_path


# --- load_config default path ---


def test_load_config_default_path_uses_gauntler_home(monkeypatch, tmp_path):
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    config = load_config()  # sem config.yaml → usa defaults
    assert config["score_threshold"] == 6.5


# --- learned blocklist merge (branches) ---


def test_load_config_no_learned_blocklist(tmp_path, monkeypatch):
    """No blocklist_learned.yaml → config proceeds without merging."""
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    assert "title_blocklist" in config


def test_load_config_learned_blocklist_empty(tmp_path, monkeypatch):
    """blocklist_learned.yaml exists but has no patterns → does not change anything."""
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    learned = tmp_path / "blocklist_learned.yaml"
    learned.write_text("title_blocklist: []\n")
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    assert config.get("title_blocklist", []) == []


def test_load_config_learned_blocklist_merges(tmp_path, monkeypatch):
    """Learned patterns are merged after the manual ones, without duplicating."""
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
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
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    from gauntler.core.config import load_config

    assert load_config()["scan_concurrency"] == 5


def test_scan_concurrency_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("scan_concurrency: 3\n")
    from gauntler.core.config import load_config

    assert load_config()["scan_concurrency"] == 3


def test_scan_batch_size_default(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    from gauntler.core.config import load_config

    assert load_config()["scan_batch_size"] == 5


# --- harden_permissions (S-07) ---


def test_harden_permissions_chmods_files_0600(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    (tmp_path / "gauntler.db").write_text("x")
    (tmp_path / "gauntler.db").chmod(0o644)
    from gauntler.core.config import harden_permissions

    warnings = harden_permissions()
    assert warnings == []
    assert oct((tmp_path / "gauntler.db").stat().st_mode)[-3:] == "600"


def test_harden_permissions_chmods_dirs_0700(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    (tmp_path / "browser-session").mkdir()
    (tmp_path / "browser-session").chmod(0o755)
    from gauntler.core.config import harden_permissions

    harden_permissions()
    assert oct((tmp_path / "browser-session").stat().st_mode)[-3:] == "700"


def test_harden_permissions_skips_missing_files(tmp_path, monkeypatch):
    """No real files in GAUNTLER_HOME → nothing to fix, no error."""
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    from gauntler.core.config import harden_permissions

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
        from gauntler.core.config import DEFAULTS

        example = Path(__file__).resolve().parents[2] / "config.example.yaml"
        user = yaml.safe_load(example.read_text()) or {}
        merged = {**DEFAULTS, "browser_session_dir": "x", "screenshots_dir": "y", **user}
        validate_config(merged)  # must not raise


def test_harden_permissions_warns_on_chmod_failure_without_raising(tmp_path, monkeypatch):
    """A permission error must never crash the server's startup — it becomes
    a warning, not an exception."""
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    (tmp_path / "profile.yaml").write_text("x")
    (tmp_path / "browser-session").mkdir()
    from gauntler.core import config as config_mod

    with patch.object(config_mod.Path, "chmod", side_effect=OSError("read-only fs")):
        warnings = config_mod.harden_permissions()

    assert len(warnings) >= 2
    assert any("profile.yaml" in w or "permiss" in w.lower() for w in warnings)
    assert any("browser-session" in w or "permiss" in w.lower() for w in warnings)
