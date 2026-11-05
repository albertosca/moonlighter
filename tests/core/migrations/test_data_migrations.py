"""The data migrations rewrite only the rows they target: m004 folds closed into archived, m005 moves job status to its application's, and m006 re-derives invented onsite values."""

from moonlighter.core.migrations import run_migrations

from tests.core.migrations.unmigrated_db import fresh_db


def test_m004_unifies_closed_into_archived(tmp_path, monkeypatch, open_dbs):
    """'closed' (good job gone from source) and 'archived' (triaged out) are one
    status from the operator's point of view — closed_at alone keeps recording
    WHY a job left the queue. m004 folds the existing 'closed' rows in.
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    db = fresh_db(tmp_path / "t.db", open_dbs)
    db.execute_sql("ALTER TABLE job ADD COLUMN status VARCHAR(32)")
    run_migrations(db)
    db.execute_sql(
        "INSERT INTO job (id, status, closed_at) VALUES (1, 'closed', '2026-08-24 12:00:00')"
    )
    db.execute_sql("UPDATE schema_version SET version = 3")

    run_migrations(db)

    status, closed_at = db.execute_sql("SELECT status, closed_at FROM job WHERE id = 1").fetchone()
    assert status == "archived"
    assert closed_at == "2026-08-24 12:00:00"


def test_m005_backfills_job_status_from_applications(tmp_path, monkeypatch, open_dbs):
    """One-shot repair for the drift found 2026-08-21: jobs still 'new' whose
    Application was already submitted/rejected. Forward writers now sync via
    sync_job_status; this folds the pre-existing rows in.
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    db = fresh_db(tmp_path / "t.db", open_dbs)
    db.execute_sql("ALTER TABLE job ADD COLUMN status VARCHAR(32)")
    db.execute_sql("ALTER TABLE application ADD COLUMN status VARCHAR(32)")
    run_migrations(db)
    db.execute_sql("INSERT INTO job (id, status) VALUES (1, 'new')")
    db.execute_sql("INSERT INTO application (id, job_id, status) VALUES (1, 1, 'submitted')")
    db.execute_sql("INSERT INTO job (id, status) VALUES (2, 'new')")
    db.execute_sql("INSERT INTO application (id, job_id, status) VALUES (2, 2, 'rejected')")
    db.execute_sql("INSERT INTO job (id, status) VALUES (3, 'new')")
    db.execute_sql("INSERT INTO application (id, job_id, status) VALUES (3, 3, 'draft')")
    db.execute_sql("UPDATE schema_version SET version = 4")

    run_migrations(db)

    rows = dict(db.execute_sql("SELECT id, status FROM job ORDER BY id").fetchall())
    assert rows == {1: "applied", 2: "rejected", 3: "new"}


def test_m006_fixes_invented_onsite_remote_types(tmp_path, monkeypatch, open_dbs):
    """The old normalize_remote_type invented 'onsite' for any location it did
    not recognize (English-only vocabulary + onsite default). Live bug iFood
    #2811: location 'Remoto', remote_type 'onsite' — and since 2026-08-24 an
    invented onsite outside Belo Horizonte is an invented deterministic
    archive. m006 re-derives the stored 'onsite' rows: PT/EN explicit terms
    win, a bare place name becomes NULL (unknown, the evaluator decides).
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    db = fresh_db(tmp_path / "t.db", open_dbs)
    db.execute_sql("ALTER TABLE job ADD COLUMN location VARCHAR(255)")
    db.execute_sql("ALTER TABLE job ADD COLUMN remote_type VARCHAR(32)")
    run_migrations(db)
    rows = [
        (1, "Remoto", "onsite", "remote"),  # the iFood case
        (2, "Híbrido - São Paulo", "onsite", "hybrid"),
        (3, "São Paulo", "onsite", None),  # bare place: unknown
        (4, "Presencial - Recife", "onsite", "onsite"),  # explicit stays
        (5, "Remote - US", "remote", "remote"),  # non-onsite rows untouched
    ]
    for job_id, location, remote_type, _ in rows:
        db.execute_sql(
            "INSERT INTO job (id, location, remote_type) VALUES (?, ?, ?)",
            (job_id, location, remote_type),
        )
    db.execute_sql("UPDATE schema_version SET version = 5")

    run_migrations(db)

    got = dict(db.execute_sql("SELECT id, remote_type FROM job ORDER BY id").fetchall())
    assert got == {job_id: want for job_id, _, _, want in rows}
