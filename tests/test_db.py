import datetime
import json
import os
import pytest
from peewee import IntegrityError
from candidatador.db import init_db, Job, Application, ScanLog


def _make_job(**kwargs):
    """Helper: cria um Job com defaults mínimos, sobrescrito por kwargs."""
    defaults = dict(
        source="greenhouse",
        company="Stripe",
        title="Senior Engineer",
        url="https://boards.greenhouse.io/stripe/jobs/123",
    )
    defaults.update(kwargs)
    return Job.create(**defaults)


def test_init_creates_tables(tmp_db):
    os.environ["CANDIDATADOR_DB_PATH"] = tmp_db
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
    os.environ["CANDIDATADOR_DB_PATH"] = tmp_db
    init_db()
    ScanLog.create(job_url="https://example.com/job/1", source="greenhouse")
    urls = {row.job_url for row in ScanLog.select()}
    assert "https://example.com/job/1" in urls
    # Second insert with same URL should raise IntegrityError
    with pytest.raises(Exception):
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
    assert before - datetime.timedelta(seconds=5) <= job.found_at <= after + datetime.timedelta(seconds=5)


def test_job_posted_at_nullable(tmp_db):
    init_db()
    job = _make_job(posted_at=None)
    results = list(Job.select().where(Job.posted_at.is_null(True)))
    assert any(r.id == job.id for r in results)


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
    assert before - datetime.timedelta(seconds=5) <= log.scanned_at <= after + datetime.timedelta(seconds=5)


def test_scanlog_same_url_different_source_raises(tmp_db):
    """ScanLog.job_url is UNIQUE regardless of source — same URL with different source raises."""
    init_db()
    ScanLog.create(job_url="https://example.com/job/dup-src", source="greenhouse")
    with pytest.raises(Exception):
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
    """_db_path() returns value of CANDIDATADOR_DB_PATH env var when set."""
    from candidatador.db import _db_path
    assert _db_path() == tmp_db
