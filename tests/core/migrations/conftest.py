"""The migration tests' fixtures: the databases a test opens, closed at teardown, and a second connection that can hold the write lock."""

import sqlite3

import pytest
from peewee import SqliteDatabase


@pytest.fixture
def open_dbs():
    """Tracks every SqliteDatabase a test opens (via fresh_db), closing each
    at teardown so no sqlite3 connection leaks past the test."""
    opened: list[SqliteDatabase] = []
    yield opened
    for db in opened:
        if not db.is_closed():
            db.close()


@pytest.fixture
def raw_locker(tmp_path):
    """Holds a genuine OS-level exclusive write lock on the DB file via a
    second, independent sqlite3 connection (BEGIN EXCLUSIVE) — the same kind
    of contention the nightly B5 writer produces. `timeout=0` means the
    lock manifests as an immediate error, not a multi-second busy-wait."""
    conn = sqlite3.connect(tmp_path / "t.db", timeout=0)
    yield conn
    conn.close()
