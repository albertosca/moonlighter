"""m011: an emailsyncrun table created before window_start existed gets the column."""

from moonlighter.core.migration_runner import run_migrations
from tests.core.migrations.unmigrated_db import fresh_db


def _columns(db):
    return {row[1] for row in db.execute_sql("PRAGMA table_info(emailsyncrun)").fetchall()}


def test_m011_adds_window_start_and_drops_the_runs_without_one(tmp_path, monkeypatch, open_dbs):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    db = fresh_db(tmp_path / "t.db", open_dbs)
    db.execute_sql(
        "CREATE TABLE emailsyncrun (id INTEGER NOT NULL PRIMARY KEY, finished_at DATETIME NOT NULL)"
    )
    db.execute_sql("INSERT INTO emailsyncrun (finished_at) VALUES ('2026-11-17 10:00:00')")
    run_migrations(db)
    assert "window_start" in _columns(db)
    assert db.execute_sql("SELECT COUNT(*) FROM emailsyncrun").fetchone() == (0,)


def test_m011_keeps_the_runs_of_a_table_that_has_the_column(tmp_path, monkeypatch, open_dbs):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    db = fresh_db(tmp_path / "t.db", open_dbs)
    db.execute_sql(
        "CREATE TABLE emailsyncrun (id INTEGER NOT NULL PRIMARY KEY, "
        "finished_at DATETIME NOT NULL, window_start DATETIME NOT NULL)"
    )
    db.execute_sql(
        "INSERT INTO emailsyncrun (finished_at, window_start) "
        "VALUES ('2026-11-17 10:00:00', '2026-10-18 10:00:00')"
    )
    run_migrations(db)
    assert db.execute_sql("SELECT COUNT(*) FROM emailsyncrun").fetchone() == (1,)


def test_m011_skips_a_database_without_the_table(tmp_path, monkeypatch, open_dbs):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    db = fresh_db(tmp_path / "t.db", open_dbs)
    run_migrations(db)
    assert _columns(db) == set()
