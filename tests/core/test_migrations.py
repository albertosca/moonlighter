import sqlite3
import time

import peewee
import pytest
from gauntler.core import migrations
from gauntler.core.migrations import MIGRATIONS, current_version, run_migrations
from peewee import SqliteDatabase


@pytest.fixture
def open_dbs():
    """Tracks every SqliteDatabase a test opens (via _fresh_db), closing each
    at teardown so no sqlite3 connection leaks past the test."""
    opened: list[SqliteDatabase] = []
    yield opened
    for db in opened:
        if not db.is_closed():
            db.close()


def _fresh_db(path, open_dbs, timeout=None):
    """A DB with the base tables (as init_db would create them) but none of
    the three columns the migrations add, and no schema_version table.

    `timeout` is forwarded to `sqlite3.connect` via peewee (default lets
    sqlite busy-wait up to 5s before raising, which the genuine-lock tests
    override to 0 so a lock raises immediately and the test stays fast)."""
    db = (
        SqliteDatabase(str(path), timeout=timeout)
        if timeout is not None
        else SqliteDatabase(str(path))
    )
    db.connect()
    open_dbs.append(db)
    db.execute_sql("CREATE TABLE application (id INTEGER PRIMARY KEY, job_id INTEGER)")
    db.execute_sql("CREATE TABLE job (id INTEGER PRIMARY KEY)")
    return db


def _real_shaped_db(path, open_dbs):
    """Simulates Alberto's real DB: email_ref/current_stage/closed_at already
    exist (from the old ad-hoc ALTERs) but there is NO schema_version table."""
    db = _fresh_db(path, open_dbs)
    db.execute_sql("ALTER TABLE application ADD COLUMN email_ref VARCHAR(8) NULL")
    db.execute_sql("ALTER TABLE application ADD COLUMN current_stage VARCHAR(255) NULL")
    db.execute_sql("ALTER TABLE job ADD COLUMN closed_at DATETIME NULL")
    return db


def _columns(db, table):
    cursor = db.execute_sql(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def test_current_version_is_zero_before_any_migration(tmp_path, open_dbs):
    db = _fresh_db(tmp_path / "t.db", open_dbs)
    assert current_version(db) == 0


def test_current_version_is_zero_when_table_exists_but_empty(tmp_path, open_dbs):
    """Defensive branch: `schema_version` exists (e.g. a torn prior run that
    created the table but never got to seed it) but holds no row. Reading it
    must still return 0, not raise — and `current_version` must not write
    anything to fix it up (it stays read-only)."""
    db = _fresh_db(tmp_path / "t.db", open_dbs)
    db.execute_sql("CREATE TABLE schema_version (version INTEGER NOT NULL)")

    assert current_version(db) == 0
    assert db.execute_sql("SELECT * FROM schema_version").fetchone() is None


def test_run_migrations_resumes_from_existing_schema_version_row(tmp_path, monkeypatch, open_dbs):
    """`schema_version` already exists and holds a row (a prior migration run
    got partway through, or completed). `_ensure_schema_version_table` must
    leave that row alone rather than re-seeding it back to 0 — only the
    still-pending migrations run, and the version continues climbing from
    where it left off."""
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path / "home"))
    db = _fresh_db(tmp_path / "t.db", open_dbs)
    db.execute_sql("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    db.execute_sql("INSERT INTO schema_version (version) VALUES (1)")
    db.execute_sql("ALTER TABLE application ADD COLUMN email_ref VARCHAR(8) NULL")

    assert current_version(db) == 1

    applied = run_migrations(db)

    assert applied == [name for _, name, _ in MIGRATIONS[1:]]
    assert current_version(db) == len(MIGRATIONS)
    assert "current_stage" in _columns(db, "application")
    assert "closed_at" in _columns(db, "job")


def test_fresh_db_applies_all_migrations(tmp_path, monkeypatch, open_dbs):
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path / "home"))
    db = _fresh_db(tmp_path / "t.db", open_dbs)

    applied = run_migrations(db)

    assert applied == [name for _, name, _ in MIGRATIONS]
    assert current_version(db) == len(MIGRATIONS)
    assert "email_ref" in _columns(db, "application")
    assert "current_stage" in _columns(db, "application")
    assert "closed_at" in _columns(db, "job")


def test_idempotence_on_real_shaped_db_never_raises(tmp_path, monkeypatch, open_dbs):
    """THE critical invariant: Alberto's real DB already has the three columns
    from the old ad-hoc ALTERs but no schema_version table (detected version 0).
    Running the migrations against it must be a safe no-op per column and
    converge to the latest version — never raise "column already exists"."""
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path / "home"))
    db = _real_shaped_db(tmp_path / "t.db", open_dbs)

    assert current_version(db) == 0

    applied = run_migrations(db)

    assert applied == [name for _, name, _ in MIGRATIONS]
    assert current_version(db) == len(MIGRATIONS) == 3
    assert "email_ref" in _columns(db, "application")
    assert "current_stage" in _columns(db, "application")
    assert "closed_at" in _columns(db, "job")


def test_second_run_is_a_no_op_and_takes_no_backup(tmp_path, monkeypatch, open_dbs):
    home = tmp_path / "home"
    monkeypatch.setenv("GAUNTLER_HOME", str(home))
    db = _fresh_db(tmp_path / "t.db", open_dbs)

    run_migrations(db)
    backups_dir = home / "backups"
    files_after_first = set(backups_dir.glob("pre-migration-*.db"))
    assert len(files_after_first) == 1

    applied_second = run_migrations(db)

    assert applied_second == []
    assert set(backups_dir.glob("pre-migration-*.db")) == files_after_first


def test_backup_taken_only_when_migrations_are_pending(tmp_path, monkeypatch, open_dbs):
    home = tmp_path / "home"
    monkeypatch.setenv("GAUNTLER_HOME", str(home))
    backups_dir = home / "backups"
    db = _fresh_db(tmp_path / "t.db", open_dbs)

    assert not backups_dir.exists()

    run_migrations(db)

    assert backups_dir.exists()
    files = list(backups_dir.glob("pre-migration-*.db"))
    assert len(files) == 1
    # The backup is a valid, independently-openable SQLite file.
    check = sqlite3.connect(files[0])
    tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master").fetchall()}
    assert "application" in tables
    assert "job" in tables
    check.close()

    # No pending migrations left: a further call takes no new backup.
    run_migrations(db)
    assert len(list(backups_dir.glob("pre-migration-*.db"))) == 1


def test_backup_retention_keeps_last_five(tmp_path, monkeypatch, open_dbs):
    home = tmp_path / "home"
    monkeypatch.setenv("GAUNTLER_HOME", str(home))
    backups_dir = home / "backups"
    backups_dir.mkdir(parents=True)
    for i in range(7):
        (backups_dir / f"pre-migration-2020010{i}-000000.db").write_text("stale")

    db = _fresh_db(tmp_path / "t.db", open_dbs)
    run_migrations(db)

    files = sorted(backups_dir.glob("pre-migration-*.db"))
    # 7 pre-existing (stale placeholders) + 1 new real backup = 8, pruned to 5.
    assert len(files) == 5
    # The newest (the just-taken real backup) must survive the prune.
    check = sqlite3.connect(files[-1])
    tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master").fetchall()}
    check.close()
    assert "application" in tables


def test_failed_migration_leaves_version_at_last_fully_applied(tmp_path, monkeypatch, open_dbs):
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path / "home"))
    db = _fresh_db(tmp_path / "t.db", open_dbs)

    def _boom(_db):
        raise peewee.OperationalError("simulated failure, not a lock")

    broken_migrations = [*MIGRATIONS, (4, "boom", _boom)]
    monkeypatch.setattr(migrations, "MIGRATIONS", broken_migrations)

    with pytest.raises(peewee.OperationalError):
        run_migrations(db)

    assert current_version(db) == len(MIGRATIONS)  # last fully-applied version, not torn


@pytest.fixture
def raw_locker(tmp_path):
    """Holds a genuine OS-level exclusive write lock on the DB file via a
    second, independent sqlite3 connection (BEGIN EXCLUSIVE) — the same kind
    of contention the nightly B5 writer produces. `timeout=0` means the
    lock manifests as an immediate error, not a multi-second busy-wait."""
    conn = sqlite3.connect(tmp_path / "t.db", timeout=0)
    yield conn
    conn.close()


def test_locked_db_retries_then_succeeds(tmp_path, monkeypatch, open_dbs, raw_locker):
    """Drives a REAL peewee-level lock (not a raised type) to prove the retry
    actually fires. `_backup` is stubbed to grab the lock at the exact
    synchronous point B5 would (right after the pre-migration backup, before
    the schema_version/migration writes) — sqlite's online backup step
    itself busy-loops against an externally-held exclusive lock indefinitely
    regardless of `timeout=0` (verified empirically), which would make the
    stub's own setup hang if the lock were taken any earlier."""
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(migrations, "_LOCK_BACKOFF_S", 0)
    db = _fresh_db(tmp_path / "t.db", open_dbs, timeout=0)

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


def test_locked_db_exhausts_retries_and_raises(tmp_path, monkeypatch, open_dbs, raw_locker):
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
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(migrations, "_LOCK_BACKOFF_S", 0)
    db = _fresh_db(tmp_path / "t.db", open_dbs, timeout=0)

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
