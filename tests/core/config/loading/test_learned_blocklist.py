from moonlighter.core.config import load_config


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
