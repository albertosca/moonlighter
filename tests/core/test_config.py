from pathlib import Path

import pytest
from candidatador.core.config import candidatador_home, load_company_list, load_config, load_profile


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


# --- candidatador_home ---


def test_candidatador_home_default(monkeypatch):
    monkeypatch.delenv("CANDIDATADOR_HOME", raising=False)
    home = candidatador_home()
    assert home == (Path.home() / ".candidatador")


def test_candidatador_home_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("CANDIDATADOR_HOME", str(tmp_path))
    assert candidatador_home() == tmp_path


# --- load_config default path ---


def test_load_config_default_path_uses_candidatador_home(monkeypatch, tmp_path):
    monkeypatch.setenv("CANDIDATADOR_HOME", str(tmp_path))
    config = load_config()  # sem config.yaml → usa defaults
    assert config["score_threshold"] == 6.5


# --- learned blocklist merge (branches) ---


def test_load_config_no_learned_blocklist(tmp_path, monkeypatch):
    """Sem blocklist_learned.yaml → config segue sem merge."""
    monkeypatch.setenv("CANDIDATADOR_HOME", str(tmp_path))
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    assert "title_blocklist" in config


def test_load_config_learned_blocklist_empty(tmp_path, monkeypatch):
    """blocklist_learned.yaml existe mas sem patterns → não altera."""
    monkeypatch.setenv("CANDIDATADOR_HOME", str(tmp_path))
    learned = tmp_path / "blocklist_learned.yaml"
    learned.write_text("title_blocklist: []\n")
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    assert config.get("title_blocklist", []) == []


def test_load_config_learned_blocklist_merges(tmp_path, monkeypatch):
    """patterns aprendidos são mesclados após os manuais, sem duplicar."""
    monkeypatch.setenv("CANDIDATADOR_HOME", str(tmp_path))
    learned = tmp_path / "blocklist_learned.yaml"
    learned.write_text("title_blocklist:\n  - recruiter\n  - intern\n")
    config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
    assert "recruiter" in config["title_blocklist"]
    assert "intern" in config["title_blocklist"]


# --- load_company_list: formatos de valor ---


def test_load_company_list_mixed_value_shapes(tmp_path):
    """Fase-dict com valor não-lista é ignorado; valor escalar vira [] (125->124, 129)."""
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
    """Quando phase é especificado, retorna apenas os slugs daquela fase."""
    company_file = tmp_path / "company_list.yaml"
    company_file.write_text(
        "greenhouse:\n"
        "  phase1:\n"
        "    - stripe\n"
        "  phase2:\n"
        "    - linear\n"
    )
    result = load_company_list(path=str(company_file), phase="phase1")
    assert result["greenhouse"] == ["stripe"]


# --- scan_concurrency ---


def test_scan_concurrency_default(tmp_path, monkeypatch):
    monkeypatch.setenv("CANDIDATADOR_HOME", str(tmp_path))
    from candidatador.core.config import load_config
    assert load_config()["scan_concurrency"] == 5


def test_scan_concurrency_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CANDIDATADOR_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("scan_concurrency: 3\n")
    from candidatador.core.config import load_config
    assert load_config()["scan_concurrency"] == 3
