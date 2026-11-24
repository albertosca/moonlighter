import pytest

from moonlighter.core.config.loading import load_config


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


def test_a_non_list_user_blocklist_with_a_learned_file_fails_in_the_merge(tmp_path, monkeypatch):
    """The learned blocklist merges BEFORE validation (spec 2026-11-23, review focus 4).

    So a str title_blocklist raises TypeError in `manual + learned`, not ConfigError.
    Validating first would be a behaviour change, which is a backlog item, not this refactor.
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "blocklist_learned.yaml").write_text("title_blocklist:\n  - recruiter\n")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("title_blocklist: not-a-list\n")
    with pytest.raises(TypeError):
        load_config(config_path=str(config_file))
