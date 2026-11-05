"""Registering an application by hand: the submitted row, its ref and its alias."""

from moonlighter.core.db import Application, Job, init_db
from moonlighter.tracking.register import RegisterKind, register_application, register_to_dict

CONFIG = {"email": {"address": "jane@example.com"}}


def _job():
    init_db()
    return Job.create(
        source="greenhouse", company="Acme", title="Eng", url="https://x/1", status="new"
    )


def test_register_creates_a_submitted_application_with_a_tracking_ref(temporary_database):
    job = _job()
    register_result = register_application(job.id, CONFIG)
    application = Application.get(Application.job == job)
    assert register_result.kind is RegisterKind.REGISTERED
    assert (register_result.application_id, register_result.status) == (application.id, "submitted")
    assert application.applied_at is not None
    assert register_result.email_ref == application.email_ref
    assert len(register_result.email_ref) == 8
    assert register_result.alias == f"jane+{register_result.email_ref}@example.com"
    assert (
        Job.get_by_id(job.id).status == "applied"
    )  # sync_job_status ran: application "submitted" -> job "applied"
    assert register_to_dict(register_result)["kind"] == "registered"


def test_register_promotes_an_existing_draft_and_keeps_its_ref(temporary_database):
    job = _job()
    Application.create(job=job, status="draft", email_ref="ab12cd34")
    register_result = register_application(job.id, CONFIG)
    assert (register_result.status, register_result.email_ref) == ("submitted", "ab12cd34")


def test_register_leaves_an_already_advanced_application_alone(temporary_database):
    job = _job()
    Application.create(job=job, status="interviews", email_ref="ab12cd34")
    register_result = register_application(job.id, CONFIG)
    assert register_result.status == "interviews"


def test_register_without_a_configured_address_has_no_alias(temporary_database):
    job = _job()
    register_result = register_application(job.id, {})
    assert register_result.kind is RegisterKind.REGISTERED
    assert register_result.alias is None
    assert register_result.email_ref is not None


def test_register_unknown_job(temporary_database):
    init_db()
    register_result = register_application(4242, CONFIG)
    assert register_result.kind is RegisterKind.JOB_NOT_FOUND
    assert register_to_dict(register_result) == {
        "kind": "job_not_found",
        "job_id": 4242,
        "application_id": None,
        "status": None,
        "email_ref": None,
        "alias": None,
        "error": "Job 4242 not found.",
    }
