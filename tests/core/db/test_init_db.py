"""init_db creates the tables, adds the columns an older schema lacks, keeps existing rows, and ends at the latest migration version."""

from moonlighter.core.db import Application, Job, db, init_db
from moonlighter.core.migration_runner import current_version
from moonlighter.core.migrations import MIGRATIONS
from tests.core.db.sample_job import make_job


def test_init_creates_tables(temporary_database):
    init_db()
    # Tables exist and accept writes
    job = Job.create(
        source="greenhouse",
        company="Stripe",
        title="Senior Engineer",
        url="https://boards.greenhouse.io/stripe/jobs/123",
    )
    assert job.id is not None
    assert job.status == "new"


def test_init_db_migrates_old_job_table(temporary_database):
    """Old 'job' table (without closed_at) → init_db adds the column via ALTER TABLE."""
    db.init(temporary_database)
    db.connect(reuse_if_open=True)
    db.execute_sql("DROP TABLE IF EXISTS job")
    db.execute_sql(
        "CREATE TABLE job (id INTEGER PRIMARY KEY, source VARCHAR(50), company VARCHAR(255), "
        "title VARCHAR(255), url VARCHAR(255) UNIQUE, status VARCHAR(50))"
    )
    db.close()

    init_db()  # runs the safe migration

    cursor = db.execute_sql("PRAGMA table_info(job)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "closed_at" in columns


def test_init_db_idempotent_preserves_email_ref(temporary_database):
    """Calling init_db() twice does not erase existing data."""
    init_db()
    job = make_job()
    Application.create(job=job, email_ref="persist01", current_stage="live_coding")
    init_db()  # second call — safe migration
    saved = Application.get_by_id(1)
    assert saved.email_ref == "persist01"
    assert saved.current_stage == "live_coding"


def test_init_db_migrates_old_application_table(temporary_database):
    """Old 'application' table (with no email_ref/current_stage) → init_db adds
    the columns via ALTER TABLE (migrations.py: _m001_application_email_ref,
    _m002_application_current_stage).
    """
    db.init(temporary_database)
    db.connect(reuse_if_open=True)
    db.execute_sql("DROP TABLE IF EXISTS application")
    db.execute_sql("CREATE TABLE application (id INTEGER PRIMARY KEY, status VARCHAR(50))")
    db.close()

    init_db()  # runs the safe migration

    cursor = db.execute_sql("PRAGMA table_info(application)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "email_ref" in columns
    assert "current_stage" in columns


# --- init_db delegates schema evolution to run_migrations (E7 T2) ─────────────


def test_init_db_fresh_db_reaches_latest_version_with_all_columns(temporary_database):
    """A fresh temp DB, after init_db(), is at the latest schema_version and has every
    column the migrations add (behavior-preserving vs. the old inline ALTERs).
    """
    init_db()

    assert current_version(db) == len(MIGRATIONS)
    application_columns = {
        row[1] for row in db.execute_sql("PRAGMA table_info(application)").fetchall()
    }
    assert "email_ref" in application_columns
    assert "current_stage" in application_columns
    job_columns = {row[1] for row in db.execute_sql("PRAGMA table_info(job)").fetchall()}
    assert "closed_at" in job_columns


def test_init_db_called_twice_stays_at_latest_version(temporary_database):
    """Calling init_db() a second time is a no-op: no error, version unchanged."""
    init_db()
    init_db()

    assert current_version(db) == len(MIGRATIONS)


def test_init_db_converges_real_db_shape_without_schema_version(temporary_database):
    """A DB that already has the migrated columns (the real ~/.moonlighter shape,
    pre-existing before this schema_version table existed) converges to the latest
    version with no error — run_migrations must not choke on already-applied columns.
    """
    db.init(temporary_database)
    db.connect(reuse_if_open=True)
    db.execute_sql(
        "CREATE TABLE application (id INTEGER PRIMARY KEY, status VARCHAR(50), "
        "email_ref VARCHAR(8), current_stage VARCHAR(255))"
    )
    db.execute_sql(
        "CREATE UNIQUE INDEX application_email_ref "
        "ON application (email_ref) WHERE email_ref IS NOT NULL"
    )
    db.execute_sql(
        "CREATE TABLE job (id INTEGER PRIMARY KEY, source VARCHAR(50), company VARCHAR(255), "
        "title VARCHAR(255), url VARCHAR(255) UNIQUE, status VARCHAR(50), closed_at DATETIME)"
    )
    db.close()

    init_db()

    assert current_version(db) == len(MIGRATIONS)
