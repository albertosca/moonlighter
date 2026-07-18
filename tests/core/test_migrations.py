import sqlite3

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


def _fresh_db(path, open_dbs):
    """A DB with the base tables (as init_db would create them) but none of
    the three columns the migrations add, and no schema_version table."""
    db = SqliteDatabase(str(path))
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
        raise sqlite3.OperationalError("simulated failure, not a lock")

    broken_migrations = [*MIGRATIONS, (4, "boom", _boom)]
    monkeypatch.setattr(migrations, "MIGRATIONS", broken_migrations)

    with pytest.raises(sqlite3.OperationalError):
        run_migrations(db)

    assert current_version(db) == len(MIGRATIONS)  # last fully-applied version, not torn


def test_locked_db_retries_then_succeeds(tmp_path, monkeypatch, open_dbs):
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path / "home"))
    db = _fresh_db(tmp_path / "t.db", open_dbs)

    calls = {"n": 0}
    real_m001 = migrations._m001_application_email_ref

    def _flaky_m001(db_):
        calls["n"] += 1
        if calls["n"] < 3:
            raise sqlite3.OperationalError("database is locked")
        real_m001(db_)

    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        [
            (1, "application_email_ref", _flaky_m001),
            *MIGRATIONS[1:],
        ],
    )
    monkeypatch.setattr(migrations, "_LOCK_BACKOFF_S", 0)

    applied = run_migrations(db)

    assert calls["n"] == 3
    assert applied == [name for _, name, _ in MIGRATIONS]
    assert current_version(db) == len(MIGRATIONS)


def test_locked_db_exhausts_retries_and_raises(tmp_path, monkeypatch, open_dbs):
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path / "home"))
    db = _fresh_db(tmp_path / "t.db", open_dbs)

    def _always_locked(_db):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        [(1, "always_locked", _always_locked)],
    )
    monkeypatch.setattr(migrations, "_LOCK_BACKOFF_S", 0)

    with pytest.raises(sqlite3.OperationalError):
        run_migrations(db)

    assert current_version(db) == 0
