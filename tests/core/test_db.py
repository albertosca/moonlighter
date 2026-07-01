import datetime
import json
import os

import pytest
from gauntler.core.db import Application, Job, ScanLog, init_db
from peewee import IntegrityError


def _make_job(**kwargs):
    """Helper: cria um Job com defaults mínimos, sobrescrito por kwargs."""
    defaults = {
        "source": "greenhouse",
        "company": "Stripe",
        "title": "Senior Engineer",
        "url": "https://boards.greenhouse.io/stripe/jobs/123",
    }
    defaults.update(kwargs)
    return Job.create(**defaults)


def test_init_creates_tables(tmp_db):
    os.environ["GAUNTLER_DB_PATH"] = tmp_db
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
    os.environ["GAUNTLER_DB_PATH"] = tmp_db
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
    os.environ["GAUNTLER_DB_PATH"] = tmp_db
    init_db()
    job = _make_job()
    assert job.closed_at is None


def test_job_closed_at_stored_and_retrieved(tmp_db):
    os.environ["GAUNTLER_DB_PATH"] = tmp_db
    init_db()
    when = datetime.datetime(2026, 7, 1, 12, 0, 0)
    job = _make_job(status="closed", closed_at=when)
    saved = Job.get_by_id(job.id)
    assert saved.status == "closed"
    assert saved.closed_at == when


def test_init_db_migrates_old_job_table(tmp_db):
    """Old 'job' table (without closed_at) → init_db adds the column via ALTER TABLE."""
    from gauntler.core.db import db

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
    """_db_path() returns value of GAUNTLER_DB_PATH env var when set."""
    from gauntler.core.db import _db_path

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
    """email_ref é UNIQUE — dois apps com mesmo ref levantam IntegrityError."""
    from peewee import IntegrityError

    init_db()
    job = _make_job()
    Application.create(job=job, email_ref="abc123")
    with pytest.raises(IntegrityError):
        Application.create(job=_make_job(url="https://x.com/2"), email_ref="abc123")


def test_application_email_ref_none_not_constrained(tmp_db):
    """Múltiplos apps sem ref (null) devem coexistir sem violar unicidade."""
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
    """'interviews' (plural) é o status correto para etapas de entrevista."""
    init_db()
    job = _make_job()
    app = Application.create(job=job, status="interviews")
    assert Application.get_by_id(app.id).status == "interviews"


def test_init_db_idempotent_preserves_email_ref(tmp_db):
    """Chamar init_db() duas vezes não apaga dados existentes."""
    init_db()
    job = _make_job()
    Application.create(job=job, email_ref="persist01", current_stage="live_coding")
    init_db()  # segunda chamada — migration segura
    saved = Application.get_by_id(1)
    assert saved.email_ref == "persist01"
    assert saved.current_stage == "live_coding"


def test_application_email_ref_lookup_by_ref(tmp_db):
    """Deve ser possível recuperar uma Application pelo email_ref."""
    init_db()
    job = _make_job()
    Application.create(job=job, email_ref="lkp001")
    found = Application.get(Application.email_ref == "lkp001")
    assert found.email_ref == "lkp001"


def test_init_db_migrates_old_application_table(tmp_db):
    """Tabela 'application' antiga (sem email_ref/current_stage) → init_db adiciona
    as colunas via ALTER TABLE (db.py:98-99, 104)."""
    from gauntler.core.db import db

    db.init(tmp_db)
    db.connect(reuse_if_open=True)
    db.execute_sql("DROP TABLE IF EXISTS application")
    db.execute_sql("CREATE TABLE application (id INTEGER PRIMARY KEY, status VARCHAR(50))")
    db.close()

    init_db()  # roda a migração segura

    cursor = db.execute_sql("PRAGMA table_info(application)")
    cols = {row[1] for row in cursor.fetchall()}
    assert "email_ref" in cols
    assert "current_stage" in cols


def test_db_path_default_when_env_unset(monkeypatch):
    """Sem GAUNTLER_DB_PATH nem GAUNTLER_HOME → default ~/.gauntler/gauntler.db."""
    from gauntler.core.db import _db_path

    monkeypatch.delenv("GAUNTLER_DB_PATH", raising=False)
    monkeypatch.delenv("GAUNTLER_HOME", raising=False)
    assert _db_path().endswith("/.gauntler/gauntler.db")


def test_db_path_respects_env(monkeypatch):
    from gauntler.core.db import _db_path

    monkeypatch.setenv("GAUNTLER_DB_PATH", "/tmp/custom-gauntler.db")
    assert _db_path() == "/tmp/custom-gauntler.db"


def test_db_path_follows_gauntler_home(monkeypatch, tmp_path):
    """Sem GAUNTLER_DB_PATH, o banco segue GAUNTLER_HOME (fonte única)."""
    from gauntler.core.db import _db_path

    monkeypatch.delenv("GAUNTLER_DB_PATH", raising=False)
    monkeypatch.setenv("GAUNTLER_HOME", str(tmp_path))
    assert _db_path() == str(tmp_path / "gauntler.db")
