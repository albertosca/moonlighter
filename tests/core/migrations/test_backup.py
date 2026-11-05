"""run_migrations takes a readable pre-migration backup only when a migration is pending, and keeps the newest five."""

import sqlite3

from moonlighter.core.migration_runner import run_migrations
from tests.core.migrations.unmigrated_db import fresh_db


def test_second_run_is_a_no_op_and_takes_no_backup(tmp_path, monkeypatch, open_dbs):
    home = tmp_path / "home"
    monkeypatch.setenv("MOONLIGHTER_HOME", str(home))
    db = fresh_db(tmp_path / "t.db", open_dbs)

    run_migrations(db)
    backups_directory = home / "backups"
    files_after_first = set(backups_directory.glob("pre-migration-*.db"))
    assert len(files_after_first) == 1

    applied_second = run_migrations(db)

    assert applied_second == []
    assert set(backups_directory.glob("pre-migration-*.db")) == files_after_first


def test_backup_taken_only_when_migrations_are_pending(tmp_path, monkeypatch, open_dbs):
    home = tmp_path / "home"
    monkeypatch.setenv("MOONLIGHTER_HOME", str(home))
    backups_directory = home / "backups"
    db = fresh_db(tmp_path / "t.db", open_dbs)

    assert not backups_directory.exists()

    run_migrations(db)

    assert backups_directory.exists()
    files = list(backups_directory.glob("pre-migration-*.db"))
    assert len(files) == 1
    # The backup is a valid, independently-openable SQLite file.
    check = sqlite3.connect(files[0])
    tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master").fetchall()}
    assert "application" in tables
    assert "job" in tables
    check.close()

    # No pending migrations left: a further call takes no new backup.
    run_migrations(db)
    assert len(list(backups_directory.glob("pre-migration-*.db"))) == 1


def test_backup_retention_keeps_last_five(tmp_path, monkeypatch, open_dbs):
    home = tmp_path / "home"
    monkeypatch.setenv("MOONLIGHTER_HOME", str(home))
    backups_directory = home / "backups"
    backups_directory.mkdir(parents=True)
    for index in range(7):
        (backups_directory / f"pre-migration-2020010{index}-000000.db").write_text("stale")

    db = fresh_db(tmp_path / "t.db", open_dbs)
    run_migrations(db)

    files = sorted(backups_directory.glob("pre-migration-*.db"))
    # 7 pre-existing (stale placeholders) + 1 new real backup = 8, pruned to 5.
    assert len(files) == 5
    # The newest (the just-taken real backup) must survive the prune.
    check = sqlite3.connect(files[-1])
    tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master").fetchall()}
    check.close()
    assert "application" in tables
