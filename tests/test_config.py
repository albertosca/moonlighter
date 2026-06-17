import pytest

from candidatador.config import _PROJECT_ROOT, load_company_list, load_config, load_profile


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
    assert "~" not in config["db_path"]
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
    for key in ("db_path", "browser_session_dir", "screenshots_dir"):
        assert "~" not in config[key], f"{key} still contains '~'"


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


# --- _PROJECT_ROOT ---


def test_project_root_is_absolute():
    assert _PROJECT_ROOT.is_absolute(), "_PROJECT_ROOT is not an absolute path"
    assert ".." not in _PROJECT_ROOT.parts, "_PROJECT_ROOT contains '..'"


# --- load_config default path ---


def test_load_config_default_path_finds_project_config():
    config = load_config()
    assert config["llm_model"] == "claude-sonnet-4-6"
