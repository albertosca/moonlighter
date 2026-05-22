import pytest
import tempfile
import os
from peewee import SqliteDatabase

@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Replace DB_PATH with a temp file for each test."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("CANDIDATADOR_DB_PATH", db_path)
    return db_path
