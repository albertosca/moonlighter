"""m007-m010: the reply-mailbox flag, the dedup columns, the hash backfill and the hand marks."""

from moonlighter.core.dedup import description_hash
from moonlighter.core.migration_runner import run_migrations
from tests.core.migrations.unmigrated_db import fresh_db


def _prepared(tmp_path, monkeypatch, open_dbs):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    db = fresh_db(tmp_path / "t.db", open_dbs)
    for column in ("status VARCHAR(32)", "description TEXT", "score_notes TEXT"):
        db.execute_sql(f"ALTER TABLE job ADD COLUMN {column}")
    db.execute_sql("ALTER TABLE application ADD COLUMN status VARCHAR(32)")
    return db


def test_m007_to_m010_add_the_columns_and_backfill(tmp_path, monkeypatch, open_dbs):
    db = _prepared(tmp_path, monkeypatch, open_dbs)
    run_migrations(db)
    db.execute_sql("INSERT INTO job (id, description, score_notes) VALUES (1, 'Same TEXT', NULL)")
    db.execute_sql(
        "INSERT INTO job (id, description, score_notes) "
        "VALUES (2, '  ', 'duplicate_of:#1 (same company)')"
    )
    db.execute_sql(
        "INSERT INTO job (id, description, score_notes) VALUES (3, NULL, 'duplicate_of:#999 (gone)')"
    )
    db.execute_sql(
        "INSERT INTO job (id, description, score_notes) VALUES (4, NULL, 'duplicate_of:# none')"
    )
    db.execute_sql("INSERT INTO application (id, job_id, status) VALUES (1, 1, 'submitted')")
    db.execute_sql("UPDATE schema_version SET version = 6")

    run_migrations(db)

    rows = db.execute_sql(
        "SELECT id, description_hash, duplicate_of_id FROM job ORDER BY id"
    ).fetchall()
    assert rows == [
        (1, description_hash("same text"), None),
        (2, None, 1),
        (3, None, None),
        (4, None, None),
    ]
    flag = db.execute_sql("SELECT reply_mailbox_unswept FROM application WHERE id = 1").fetchone()
    assert flag == (0,)


def test_m007_to_m010_run_twice_without_error(tmp_path, monkeypatch, open_dbs):
    db = _prepared(tmp_path, monkeypatch, open_dbs)
    run_migrations(db)
    db.execute_sql("UPDATE schema_version SET version = 6")
    run_migrations(db)
    index_names = {row[1] for row in db.execute_sql("PRAGMA index_list(job)").fetchall()}
    assert "job_description_hash" in index_names


def test_m009_and_m010_skip_a_job_table_without_text_columns(tmp_path, monkeypatch, open_dbs):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    db = fresh_db(tmp_path / "t.db", open_dbs)
    run_migrations(db)
    columns = {row[1] for row in db.execute_sql("PRAGMA table_info(job)").fetchall()}
    assert {"description_hash", "duplicate_of_id"} <= columns


def test_m010_never_points_a_job_at_itself(tmp_path, monkeypatch, open_dbs):
    db = _prepared(tmp_path, monkeypatch, open_dbs)
    run_migrations(db)
    db.execute_sql(
        "INSERT INTO job (id, description, score_notes) VALUES (5, NULL, 'duplicate_of:#5 typo')"
    )
    db.execute_sql("UPDATE schema_version SET version = 9")
    run_migrations(db)
    assert db.execute_sql("SELECT duplicate_of_id FROM job WHERE id = 5").fetchone() == (None,)
