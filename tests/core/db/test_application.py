"""The Application model defaults status to "draft", stores its form data, notes and email fields, and keeps email_ref unique only when set."""

import pytest
from peewee import IntegrityError

from moonlighter.core.db import Application, init_db
from tests.core.db.sample_job import make_job


def test_application_create_default_status(temporary_database):
    init_db()
    job = make_job()
    app = Application.create(job=job)
    assert app.status == "draft"


def test_application_get_form_data_valid(temporary_database):
    init_db()
    job = make_job()
    app = Application.create(job=job, form_data='{"Why Stripe?": "Great mission"}')
    data = app.get_form_data()
    assert data["Why Stripe?"] == "Great mission"


def test_application_get_form_data_null(temporary_database):
    init_db()
    job = make_job()
    app = Application.create(job=job)  # form_data not set → None
    assert app.get_form_data() == {}


def test_application_job_fk(temporary_database):
    init_db()
    job = make_job()
    app = Application.create(job=job)
    saved = Application.get_by_id(app.id)
    assert saved.job.id == job.id
    assert saved.job.company == job.company


def test_application_notes_accumulation(temporary_database):
    init_db()
    job = make_job()
    app = Application.create(job=job, notes=None)
    app.notes = "first note"
    app.save()
    app.notes = app.notes + " | second note"
    app.save()
    saved = Application.get_by_id(app.id)
    assert "first note" in saved.notes
    assert "second note" in saved.notes


def test_application_applied_at_nullable(temporary_database):
    """Application.applied_at defaults to None (not set at draft time)."""
    init_db()
    job = make_job()
    app = Application.create(job=job)
    saved = Application.get_by_id(app.id)
    assert saved.applied_at is None


def test_application_next_action_stored(temporary_database):
    """Application.next_action field can be stored and retrieved."""
    init_db()
    job = make_job()
    app = Application.create(job=job, next_action="Follow up on 2026-06-01")
    saved = Application.get_by_id(app.id)
    assert saved.next_action == "Follow up on 2026-06-01"


def test_application_email_ref_stored_and_retrieved(temporary_database):
    init_db()
    job = make_job()
    app = Application.create(job=job, email_ref="x7k2mp")
    saved = Application.get_by_id(app.id)
    assert saved.email_ref == "x7k2mp"


def test_application_email_ref_is_null_by_default(temporary_database):
    init_db()
    job = make_job()
    app = Application.create(job=job)
    saved = Application.get_by_id(app.id)
    assert saved.email_ref is None


def test_application_email_ref_unique_constraint(temporary_database):
    """email_ref is UNIQUE — two apps with the same ref raise IntegrityError."""
    init_db()
    job = make_job()
    Application.create(job=job, email_ref="abc123")
    with pytest.raises(IntegrityError):
        Application.create(job=make_job(url="https://x.com/2"), email_ref="abc123")


def test_application_email_ref_none_not_constrained(temporary_database):
    """Multiple apps with no ref (null) must coexist without violating uniqueness."""
    init_db()
    job1 = make_job(url="https://x.com/1")
    job2 = make_job(url="https://x.com/2")
    Application.create(job=job1, email_ref=None)
    Application.create(job=job2, email_ref=None)
    assert Application.select().where(Application.email_ref.is_null(is_null=True)).count() == 2


def test_application_current_stage_stored_and_retrieved(temporary_database):
    init_db()
    job = make_job()
    app = Application.create(job=job, current_stage="technical_interview")
    saved = Application.get_by_id(app.id)
    assert saved.current_stage == "technical_interview"


def test_application_current_stage_is_null_by_default(temporary_database):
    init_db()
    job = make_job()
    app = Application.create(job=job)
    assert Application.get_by_id(app.id).current_stage is None


def test_application_status_interviews_is_valid(temporary_database):
    """'interviews' (plural) is the correct status for interview stages."""
    init_db()
    job = make_job()
    app = Application.create(job=job, status="interviews")
    assert Application.get_by_id(app.id).status == "interviews"


def test_application_email_ref_lookup_by_ref(temporary_database):
    """It must be possible to look up an Application by email_ref."""
    init_db()
    job = make_job()
    Application.create(job=job, email_ref="lkp001")
    found = Application.get(Application.email_ref == "lkp001")
    assert found.email_ref == "lkp001"
