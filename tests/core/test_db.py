import datetime
import json
import os

import pytest
from moonlighter.core.db import Application, Job, ScanLog, init_db
from moonlighter.core.migrations import MIGRATIONS
from peewee import IntegrityError


def _make_job(**kwargs):
    """Helper: creates a Job with minimal defaults, overridden by kwargs."""
    defaults = {
        "source": "greenhouse",
        "company": "Stripe",
        "title": "Senior Engineer",
        "url": "https://boards.greenhouse.io/stripe/jobs/123",
    }
    defaults.update(kwargs)
    return Job.create(**defaults)


def test_init_creates_tables(tmp_db):
    os.environ["MOONLIGHTER_DB_PATH"] = tmp_db
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


def test_scan_log_dedup(tmp_db):
    os.environ["MOONLIGHTER_DB_PATH"] = tmp_db
    init_db()
    ScanLog.create(job_url="https://example.com/job/1", source="greenhouse")
    urls = {row.job_url for row in ScanLog.select()}
    assert "https://example.com/job/1" in urls
    # Second insert with same URL should raise IntegrityError
    with pytest.raises(IntegrityError):
        ScanLog.create(job_url="https://example.com/job/1", source="greenhouse")


# --- Job: salary fields ---


def test_job_salary_fields(tmp_db):
    init_db()
    job = _make_job(
        salary_min=150000,
        salary_max=200000,
        salary_currency="USD",
        salary_source="stated",
    )
    saved = Job.get_by_id(job.id)
    assert saved.salary_min == 150000
    assert saved.salary_max == 200000
    assert saved.salary_currency == "USD"
    assert saved.salary_source == "stated"


# --- Job: nullable fields ---


def test_job_nullable_fields_default_none(tmp_db):
    init_db()
    job = _make_job()
    saved = Job.get_by_id(job.id)
    assert saved.location is None
    assert saved.remote_type is None
    assert saved.posted_at is None
    assert saved.score is None


# --- Job: status default ---


def test_job_status_default(tmp_db):
    init_db()
    job = _make_job()
    assert job.status == "new"


# --- Job: unique URL ---


def test_job_url_unique_raises(tmp_db):
    init_db()
    _make_job(url="https://example.com/job/dup")
    with pytest.raises(IntegrityError):
        _make_job(url="https://example.com/job/dup")


# --- Job: get_caveats ---


def test_job_get_caveats_valid_json(tmp_db):
    init_db()
    job = _make_job(caveats='["US only", "requires relocation"]')
    assert job.get_caveats() == ["US only", "requires relocation"]


def test_job_get_caveats_empty_string(tmp_db):
    init_db()
    job = _make_job(caveats="")
    assert job.get_caveats() == []


def test_job_get_caveats_null(tmp_db):
    init_db()
    job = _make_job()  # caveats not set → None
    assert job.get_caveats() == []


def test_job_get_caveats_invalid_json(tmp_db):
    init_db()
    job = _make_job(caveats="not json")
    with pytest.raises(json.JSONDecodeError):
        job.get_caveats()


# --- Job: timestamps ---


def test_job_found_at_is_recent(tmp_db):
    init_db()
    before = datetime.datetime.now()
    job = _make_job()
    after = datetime.datetime.now()
    assert (
        before - datetime.timedelta(seconds=5)
        <= job.found_at
        <= after + datetime.timedelta(seconds=5)
    )


def test_job_posted_at_nullable(tmp_db):
    init_db()
    job = _make_job(posted_at=None)
    results = list(Job.select().where(Job.posted_at.is_null(True)))
    assert any(r.id == job.id for r in results)


def test_job_closed_at_is_null_by_default(tmp_db):
    os.environ["MOONLIGHTER_DB_PATH"] = tmp_db
    init_db()
    job = _make_job()
    assert job.closed_at is None


def test_job_closed_at_stored_and_retrieved(tmp_db):
    os.environ["MOONLIGHTER_DB_PATH"] = tmp_db
    init_db()
    when = datetime.datetime(2026, 7, 1, 12, 0, 0)
    job = _make_job(status="archived", closed_at=when)
    saved = Job.get_by_id(job.id)
    assert saved.status == "archived"
    assert saved.closed_at == when


def test_init_db_migrates_old_job_table(tmp_db):
    """Old 'job' table (without closed_at) → init_db adds the column via ALTER TABLE."""
    from moonlighter.core.db import db

    db.init(tmp_db)
    db.connect(reuse_if_open=True)
    db.execute_sql("DROP TABLE IF EXISTS job")
    db.execute_sql(
        "CREATE TABLE job (id INTEGER PRIMARY KEY, source VARCHAR(50), company VARCHAR(255), "
        "title VARCHAR(255), url VARCHAR(255) UNIQUE, status VARCHAR(50))"
    )
    db.close()

    init_db()  # runs the safe migration

    cursor = db.execute_sql("PRAGMA table_info(job)")
    cols = {row[1] for row in cursor.fetchall()}
    assert "closed_at" in cols


# --- Application ---


def test_application_create_default_status(tmp_db):
    init_db()
    job = _make_job()
    app = Application.create(job=job)
    assert app.status == "draft"


def test_application_get_form_data_valid(tmp_db):
    init_db()
    job = _make_job()
    app = Application.create(job=job, form_data='{"Why Stripe?": "Great mission"}')
    data = app.get_form_data()
    assert data["Why Stripe?"] == "Great mission"


def test_application_get_form_data_null(tmp_db):
    init_db()
    job = _make_job()
    app = Application.create(job=job)  # form_data not set → None
    assert app.get_form_data() == {}


def test_application_job_fk(tmp_db):
    init_db()
    job = _make_job()
    app = Application.create(job=job)
    saved = Application.get_by_id(app.id)
    assert saved.job.id == job.id
    assert saved.job.company == job.company


def test_application_notes_accumulation(tmp_db):
    init_db()
    job = _make_job()
    app = Application.create(job=job, notes=None)
    app.notes = "first note"
    app.save()
    app.notes = app.notes + " | second note"
    app.save()
    saved = Application.get_by_id(app.id)
    assert "first note" in saved.notes
    assert "second note" in saved.notes


# --- ScanLog: timestamp ---


def test_scanlog_scanned_at_is_recent(tmp_db):
    init_db()
    before = datetime.datetime.now()
    log = ScanLog.create(job_url="https://example.com/job/ts", source="greenhouse")
    after = datetime.datetime.now()
    assert (
        before - datetime.timedelta(seconds=5)
        <= log.scanned_at
        <= after + datetime.timedelta(seconds=5)
    )


def test_scanlog_same_url_different_source_raises(tmp_db):
    """ScanLog.job_url is UNIQUE regardless of source — same URL with different source raises."""
    init_db()
    ScanLog.create(job_url="https://example.com/job/dup-src", source="greenhouse")
    with pytest.raises(IntegrityError):
        ScanLog.create(job_url="https://example.com/job/dup-src", source="lever")


def test_application_applied_at_nullable(tmp_db):
    """Application.applied_at defaults to None (not set at draft time)."""
    init_db()
    job = _make_job()
    app = Application.create(job=job)
    saved = Application.get_by_id(app.id)
    assert saved.applied_at is None


def test_application_next_action_stored(tmp_db):
    """Application.next_action field can be stored and retrieved."""
    init_db()
    job = _make_job()
    app = Application.create(job=job, next_action="Follow up on 2026-06-01")
    saved = Application.get_by_id(app.id)
    assert saved.next_action == "Follow up on 2026-06-01"


def test_job_salary_notes_field(tmp_db):
    """Job.salary_notes is stored and retrievable."""
    init_db()
    job = _make_job(salary_notes="Based on Glassdoor and Levels.fyi estimates.")
    saved = Job.get_by_id(job.id)
    assert "Glassdoor" in saved.salary_notes


def test_db_path_reads_env_var(tmp_db):
    """_db_path() returns value of MOONLIGHTER_DB_PATH env var when set."""
    from moonlighter.core.db import _db_path

    assert _db_path() == tmp_db


# ── Application: campos email (email_ref + current_stage) ─────────────────────


def test_application_email_ref_stored_and_retrieved(tmp_db):
    init_db()
    job = _make_job()
    app = Application.create(job=job, email_ref="x7k2mp")
    saved = Application.get_by_id(app.id)
    assert saved.email_ref == "x7k2mp"


def test_application_email_ref_is_null_by_default(tmp_db):
    init_db()
    job = _make_job()
    app = Application.create(job=job)
    saved = Application.get_by_id(app.id)
    assert saved.email_ref is None


def test_application_email_ref_unique_constraint(tmp_db):
    """email_ref is UNIQUE — two apps with the same ref raise IntegrityError."""
    from peewee import IntegrityError

    init_db()
    job = _make_job()
    Application.create(job=job, email_ref="abc123")
    with pytest.raises(IntegrityError):
        Application.create(job=_make_job(url="https://x.com/2"), email_ref="abc123")


def test_application_email_ref_none_not_constrained(tmp_db):
    """Multiple apps with no ref (null) must coexist without violating uniqueness."""
    init_db()
    job1 = _make_job(url="https://x.com/1")
    job2 = _make_job(url="https://x.com/2")
    Application.create(job=job1, email_ref=None)
    Application.create(job=job2, email_ref=None)
    assert Application.select().where(Application.email_ref.is_null(True)).count() == 2


def test_application_current_stage_stored_and_retrieved(tmp_db):
    init_db()
    job = _make_job()
    app = Application.create(job=job, current_stage="technical_interview")
    saved = Application.get_by_id(app.id)
    assert saved.current_stage == "technical_interview"


def test_application_current_stage_is_null_by_default(tmp_db):
    init_db()
    job = _make_job()
    app = Application.create(job=job)
    assert Application.get_by_id(app.id).current_stage is None


def test_application_status_interviews_is_valid(tmp_db):
    """'interviews' (plural) is the correct status for interview stages."""
    init_db()
    job = _make_job()
    app = Application.create(job=job, status="interviews")
    assert Application.get_by_id(app.id).status == "interviews"


def test_init_db_idempotent_preserves_email_ref(tmp_db):
    """Calling init_db() twice does not erase existing data."""
    init_db()
    job = _make_job()
    Application.create(job=job, email_ref="persist01", current_stage="live_coding")
    init_db()  # second call — safe migration
    saved = Application.get_by_id(1)
    assert saved.email_ref == "persist01"
    assert saved.current_stage == "live_coding"


def test_application_email_ref_lookup_by_ref(tmp_db):
    """It must be possible to look up an Application by email_ref."""
    init_db()
    job = _make_job()
    Application.create(job=job, email_ref="lkp001")
    found = Application.get(Application.email_ref == "lkp001")
    assert found.email_ref == "lkp001"


def test_init_db_migrates_old_application_table(tmp_db):
    """Old 'application' table (with no email_ref/current_stage) → init_db adds
    the columns via ALTER TABLE (db.py:98-99, 104)."""
    from moonlighter.core.db import db

    db.init(tmp_db)
    db.connect(reuse_if_open=True)
    db.execute_sql("DROP TABLE IF EXISTS application")
    db.execute_sql("CREATE TABLE application (id INTEGER PRIMARY KEY, status VARCHAR(50))")
    db.close()

    init_db()  # runs the safe migration

    cursor = db.execute_sql("PRAGMA table_info(application)")
    cols = {row[1] for row in cursor.fetchall()}
    assert "email_ref" in cols
    assert "current_stage" in cols


def test_db_path_default_when_env_unset(monkeypatch):
    """No MOONLIGHTER_DB_PATH nor MOONLIGHTER_HOME → default ~/.moonlighter/moonlighter.db."""
    from moonlighter.core.db import _db_path

    monkeypatch.delenv("MOONLIGHTER_DB_PATH", raising=False)
    monkeypatch.delenv("MOONLIGHTER_HOME", raising=False)
    assert _db_path().endswith("/.moonlighter/moonlighter.db")


def test_db_path_respects_env(monkeypatch):
    from moonlighter.core.db import _db_path

    monkeypatch.setenv("MOONLIGHTER_DB_PATH", "/tmp/custom-moonlighter.db")
    assert _db_path() == "/tmp/custom-moonlighter.db"


def test_db_path_follows_moonlighter_home(monkeypatch, tmp_path):
    """With no MOONLIGHTER_DB_PATH, the database follows MOONLIGHTER_HOME (single source)."""
    from moonlighter.core.db import _db_path

    monkeypatch.delenv("MOONLIGHTER_DB_PATH", raising=False)
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    assert _db_path() == str(tmp_path / "moonlighter.db")


# --- init_db delegates schema evolution to run_migrations (E7 T2) ─────────────


def test_init_db_fresh_db_reaches_latest_version_with_all_columns(tmp_db):
    """A fresh temp DB, after init_db(), is at schema_version 3 and has every
    column the migrations add (behavior-preserving vs. the old inline ALTERs)."""
    from moonlighter.core.db import db
    from moonlighter.core.migrations import current_version

    init_db()

    assert current_version(db) == len(MIGRATIONS)
    app_cols = {row[1] for row in db.execute_sql("PRAGMA table_info(application)").fetchall()}
    assert "email_ref" in app_cols
    assert "current_stage" in app_cols
    job_cols = {row[1] for row in db.execute_sql("PRAGMA table_info(job)").fetchall()}
    assert "closed_at" in job_cols


def test_init_db_called_twice_stays_at_latest_version(tmp_db):
    """Calling init_db() a second time is a no-op: no error, version unchanged."""
    from moonlighter.core.db import db
    from moonlighter.core.migrations import current_version

    init_db()
    init_db()

    assert current_version(db) == len(MIGRATIONS)


def test_init_db_converges_real_db_shape_without_schema_version(tmp_db):
    """A DB that already has the migrated columns (the real ~/.moonlighter shape,
    pre-existing before this schema_version table existed) converges to version
    3 with no error — run_migrations must not choke on already-applied columns."""
    from moonlighter.core.db import db
    from moonlighter.core.migrations import current_version

    db.init(tmp_db)
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


# ── sync_job_status ──────────────────────────────────────────────────────────
# Provenance: 2026-08-21 manual triage — 5 jobs still 'new' while their
# Application was already submitted/rejected; a duplicate application was
# nearly offered twice in one session. Every Application.status writer calls
# this helper so Job.status can never drift again.


def _sync_pair(tmp_db, app_status):
    os.environ["MOONLIGHTER_DB_PATH"] = tmp_db
    init_db()
    job = _make_job(status="new")
    app = Application.create(job=job, status=app_status)
    return job, app


def test_sync_job_status_submitted_marks_job_applied(tmp_db):
    from moonlighter.core.db import sync_job_status

    job, app = _sync_pair(tmp_db, "submitted")
    sync_job_status(app)
    assert Job.get_by_id(job.id).status == "applied"


def test_sync_job_status_rejected_marks_job_rejected(tmp_db):
    from moonlighter.core.db import sync_job_status

    job, app = _sync_pair(tmp_db, "rejected")
    sync_job_status(app)
    assert Job.get_by_id(job.id).status == "rejected"


def test_sync_job_status_interview_stages_mark_job_applied(tmp_db):
    from moonlighter.core.db import sync_job_status

    job, app = _sync_pair(tmp_db, "interviews")
    sync_job_status(app)
    assert Job.get_by_id(job.id).status == "applied"


def test_sync_job_status_draft_leaves_job_alone(tmp_db):
    from moonlighter.core.db import sync_job_status

    job, app = _sync_pair(tmp_db, "draft")
    sync_job_status(app)
    assert Job.get_by_id(job.id).status == "new"
