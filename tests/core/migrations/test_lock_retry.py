"""A real SQLite write lock makes run_migrations pause and retry, succeed once the lock is released, and raise after its last attempt."""

import time

import peewee
import pytest
from moonlighter.core import migrations
from moonlighter.core.migrations import MIGRATIONS, current_version, run_migrations

from tests.core.migrations.unmigrated_db import fresh_db


def test_locked_db_retries_then_succeeds(*, tmp_path, monkeypatch, open_dbs, raw_locker):
    """Drives a REAL peewee-level lock (not a raised type) to prove the retry
    actually fires. `_backup` is stubbed to grab the lock at the exact
    synchronous point B5 would (right after the pre-migration backup, before
    the schema_version/migration writes) — sqlite's online backup step
    itself busy-loops against an externally-held exclusive lock indefinitely
    regardless of `timeout=0` (verified empirically), which would make the
    stub's own setup hang if the lock were taken any earlier."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(migrations, "_LOCK_BACKOFF_S", 0)
    db = fresh_db(tmp_path / "t.db", open_dbs, timeout=0)

    monkeypatch.setattr(migrations, "_backup", lambda db: raw_locker.execute("BEGIN EXCLUSIVE"))

    sleep_calls = {"n": 0}
    real_sleep = time.sleep

    def _fake_sleep(seconds):
        sleep_calls["n"] += 1
        if sleep_calls["n"] == 2:
            # Simulate B5 finishing its write and releasing the lock.
            raw_locker.execute("COMMIT")
        real_sleep(0)

    monkeypatch.setattr(migrations.time, "sleep", _fake_sleep)

    applied = run_migrations(db)

    assert sleep_calls["n"] == 2
    assert applied == [name for _, name, _ in MIGRATIONS]
    assert current_version(db) == len(MIGRATIONS)


def test_locked_db_exhausts_retries_and_raises(*, tmp_path, monkeypatch, open_dbs, raw_locker):
    """Same genuine lock, taken right after the (stubbed) backup and held for
    the whole run (B5 never finishes): the retry budget must exhaust and
    `run_migrations` must raise, leaving `schema_version` never created
    (current_version stays 0 once the lock is released).

    Regression check for the false-green bug: with the old
    `except sqlite3.OperationalError` this test FAILS, because peewee raises
    its own `peewee.OperationalError` (a distinct type, not a subclass) and
    the old except clause never matches it — the call raises immediately on
    the very first attempt instead of retrying and exhausting the budget.
    Confirmed by temporarily reverting the except clause to
    `sqlite3.OperationalError` and re-running this test: it failed with
    `sleep_calls["n"] == 0` instead of the expected `_LOCK_RETRIES - 1`.
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(migrations, "_LOCK_BACKOFF_S", 0)
    db = fresh_db(tmp_path / "t.db", open_dbs, timeout=0)

    monkeypatch.setattr(migrations, "_backup", lambda db: raw_locker.execute("BEGIN EXCLUSIVE"))

    sleep_calls = {"n": 0}
    real_sleep = time.sleep

    def _fake_sleep(seconds):
        sleep_calls["n"] += 1
        real_sleep(0)

    monkeypatch.setattr(migrations.time, "sleep", _fake_sleep)

    with pytest.raises(peewee.OperationalError, match="locked"):
        run_migrations(db)

    assert sleep_calls["n"] == migrations._LOCK_RETRIES - 1

    raw_locker.execute("ROLLBACK")  # release the lock so we can inspect state
    assert current_version(db) == 0
