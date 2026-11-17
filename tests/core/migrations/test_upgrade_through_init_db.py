"""init_db() on a database from before m007: the upgrade a real user runs, not run_migrations alone."""

import sqlite3
from contextlib import closing

from moonlighter.core.db import db, init_db

_JOB_VERSION_6 = (
    'CREATE TABLE "job" ("id" INTEGER NOT NULL PRIMARY KEY, "source" VARCHAR(255) NOT NULL, '
    '"company" VARCHAR(255) NOT NULL, "title" VARCHAR(255) NOT NULL, "url" VARCHAR(255) NOT NULL, '
    '"location" VARCHAR(255), "remote_type" VARCHAR(255), "description" TEXT, "posted_at" DATETIME, '
    '"score" REAL, "score_notes" TEXT, "caveats" TEXT, "salary_min" INTEGER, "salary_max" INTEGER, '
    '"salary_currency" VARCHAR(255), "salary_source" VARCHAR(255), "salary_notes" TEXT, '
    '"status" VARCHAR(255) NOT NULL, "found_at" DATETIME NOT NULL, "closed_at" DATETIME)'
)


def _downgrade_to_version_6(path: str) -> None:
    """Rebuild the tables m007-m010 change the way a version-6 database has them, with rows."""
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("DROP TABLE job")
        connection.execute(_JOB_VERSION_6)
        connection.executescript(
            """
            CREATE UNIQUE INDEX "job_url" ON "job" ("url");
            ALTER TABLE application DROP COLUMN reply_mailbox_unswept;
            UPDATE schema_version SET version = 6;
            INSERT INTO job (id, source, company, title, url, status, description, found_at)
            VALUES (1, 'greenhouse', 'Acme', 'Engineer', 'https://x.com/1', 'new',
                    'Build things.', '2026-11-01 10:00:00'),
                   (2, 'lever', 'Beta', 'Lead', 'https://x.com/2', 'archived',
                    NULL, '2026-11-02 10:00:00');
            """
        )
        connection.commit()


def test_init_db_upgrades_a_version_6_database_without_corrupting_it(
    temporary_database, tmp_path, monkeypatch
):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    init_db()
    db.close()
    _downgrade_to_version_6(temporary_database)

    init_db()
    db.close()

    with closing(sqlite3.connect(temporary_database)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("SELECT version FROM schema_version").fetchone() == (10,)
    assert _dedup_indexes(temporary_database) == {
        "job_description_hash": "description_hash",
        "job_duplicate_of_id": "duplicate_of_id",
    }


def _dedup_indexes(path: str) -> dict[str, str]:
    """Each dedup index, by name, with the one column it really covers."""
    with closing(sqlite3.connect(path)) as connection:
        return {
            name: connection.execute(f"PRAGMA index_info({name})").fetchone()[2]
            for name in ("job_description_hash", "job_duplicate_of_id")
            if connection.execute(f"PRAGMA index_info({name})").fetchone() is not None
        }


def test_a_fresh_database_gets_both_dedup_indexes(temporary_database, tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    init_db()
    db.close()
    assert _dedup_indexes(temporary_database) == {
        "job_description_hash": "description_hash",
        "job_duplicate_of_id": "duplicate_of_id",
    }
