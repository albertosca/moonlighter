"""db_path prefers MOONLIGHTER_DB_PATH, then MOONLIGHTER_HOME, then the ~/.moonlighter default."""

from moonlighter.core.db import db_path


def test_db_path_reads_env_var(temporary_database):
    """db_path() returns value of MOONLIGHTER_DB_PATH env var when set."""
    assert db_path() == temporary_database


def test_db_path_default_when_env_unset(monkeypatch):
    """No MOONLIGHTER_DB_PATH nor MOONLIGHTER_HOME → default ~/.moonlighter/moonlighter.db."""
    monkeypatch.delenv("MOONLIGHTER_DB_PATH", raising=False)
    monkeypatch.delenv("MOONLIGHTER_HOME", raising=False)
    assert db_path().endswith("/.moonlighter/moonlighter.db")


def test_db_path_respects_env(monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_DB_PATH", "/tmp/custom-moonlighter.db")
    assert db_path() == "/tmp/custom-moonlighter.db"


def test_db_path_follows_moonlighter_home(monkeypatch, tmp_path):
    """With no MOONLIGHTER_DB_PATH, the database follows MOONLIGHTER_HOME (single source)."""
    monkeypatch.delenv("MOONLIGHTER_DB_PATH", raising=False)
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    assert db_path() == str(tmp_path / "moonlighter.db")
