"""run_migrations applies only the pending migrations, resumes from a stored version, converges on a database the old ad-hoc ALTERs already changed, and stops at the last whole migration when one fails."""

import peewee
import pytest
from moonlighter.core import migrations
from moonlighter.core.migrations import MIGRATIONS, current_version, run_migrations

from tests.core.migrations.unmigrated_db import fresh_db


def _real_shaped_db(path, open_dbs):
    """Simulates Alberto's real DB: email_ref/current_stage/closed_at already
    exist (from the old ad-hoc ALTERs) but there is NO schema_version table.
    """
    db = fresh_db(path, open_dbs)
    db.execute_sql("ALTER TABLE application ADD COLUMN email_ref VARCHAR(8) NULL")
    db.execute_sql("ALTER TABLE application ADD COLUMN current_stage VARCHAR(255) NULL")
    db.execute_sql("ALTER TABLE job ADD COLUMN closed_at DATETIME NULL")
    return db


def _columns(db, table):
    cursor = db.execute_sql(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def test_run_migrations_resumes_from_existing_schema_version_row(tmp_path, monkeypatch, open_dbs):
    """`schema_version` already exists and holds a row (a prior migration run
    got partway through, or completed). `_ensure_schema_version_table` must
    leave that row alone rather than re-seeding it back to 0 — only the
    still-pending migrations run, and the version continues climbing from
    where it left off.
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    db = fresh_db(tmp_path / "t.db", open_dbs)
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
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    db = fresh_db(tmp_path / "t.db", open_dbs)

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
    converge to the latest version — never raise "column already exists".
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    db = _real_shaped_db(tmp_path / "t.db", open_dbs)

    assert current_version(db) == 0

    applied = run_migrations(db)

    assert applied == [name for _, name, _ in MIGRATIONS]
    assert current_version(db) == len(MIGRATIONS) == 6
    assert "email_ref" in _columns(db, "application")
    assert "current_stage" in _columns(db, "application")
    assert "closed_at" in _columns(db, "job")


def test_failed_migration_leaves_version_at_last_fully_applied(tmp_path, monkeypatch, open_dbs):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    db = fresh_db(tmp_path / "t.db", open_dbs)

    def _boom(_db):
        raise peewee.OperationalError("simulated failure, not a lock")

    broken_migrations = [*MIGRATIONS, (7, "boom", _boom)]
    monkeypatch.setattr(migrations, "MIGRATIONS", broken_migrations)

    with pytest.raises(peewee.OperationalError):
        run_migrations(db)

    assert current_version(db) == len(MIGRATIONS)  # last fully-applied version, not torn
