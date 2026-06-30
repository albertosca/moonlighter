import pytest


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Replace DB_PATH with a temp file for each test."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("GAUNTLER_DB_PATH", db_path)
    return db_path
