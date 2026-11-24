"""Registering an application by hand: the submitted row, its ref and its alias."""

from datetime import datetime

from moonlighter.core.config.loading import build_config
from moonlighter.core.db import Application, Job, init_db
from moonlighter.tracking.register import (
    RegisterKind,
    RegisterRequest,
    register_application,
    register_to_dict,
)

CONFIG = build_config({"email": {"address": "jane@example.com"}})
NOVEMBER_10 = datetime(2026, 11, 10)  # noqa: DTZ001 - the database stores naive local time
SEPTEMBER_1 = datetime(2026, 9, 1)  # noqa: DTZ001 - the database stores naive local time
AUGUST_1 = datetime(2026, 8, 1)  # noqa: DTZ001 - the database stores naive local time
NOVEMBER_1 = datetime(2026, 11, 1)  # noqa: DTZ001 - the database stores naive local time


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
    register_result = register_application(job.id, build_config({}))
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
        "created": False,
    }


def _archived_job_below_threshold():
    init_db()
    return Job.create(
        source="manual",
        company="Solides",
        title="AI Analyst",
        url="https://x/12638",
        status="archived",
        score=5.0,
        score_notes="below threshold",
    )


def test_a_below_threshold_job_registered_as_submitted_ends_applied_with_its_score(
    temporary_database,
):
    job = _archived_job_below_threshold()
    result = register_application(job.id, CONFIG, RegisterRequest(applied_at=NOVEMBER_10))
    stored = Job.get_by_id(job.id)
    assert (result.kind, result.created, result.status) == (
        RegisterKind.REGISTERED,
        True,
        "submitted",
    )
    assert (stored.status, stored.score, stored.score_notes) == ("applied", 5.0, "below threshold")
    assert Application.get(Application.job == job).applied_at == NOVEMBER_10


def test_register_with_another_status_and_notes(temporary_database):
    job = _archived_job_below_threshold()
    result = register_application(
        job.id, CONFIG, RegisterRequest(status="rejected", notes="rejected by email")
    )
    application = Application.get(Application.job == job)
    assert result.status == "rejected"
    assert Job.get_by_id(job.id).status == "rejected"
    assert application.notes.endswith("] rejected by email")


def test_an_existing_rejected_row_is_never_overwritten(temporary_database):
    job = _job()
    Application.create(
        job=job, status="rejected", notes="[2026-10-01] no", email_ref="ab12cd34", applied_at=None
    )
    result = register_application(
        job.id,
        CONFIG,
        RegisterRequest(status="submitted", notes="typed again", applied_at=SEPTEMBER_1),
    )
    application = Application.get(Application.job == job)
    assert (result.created, result.status) == (False, "rejected")
    assert application.status == "rejected"
    assert application.applied_at == SEPTEMBER_1  # was null and a date was given
    assert application.notes.startswith("[2026-10-01] no\n[")
    assert application.email_ref == "ab12cd34"


def test_an_existing_row_without_a_given_date_keeps_applied_at_null(temporary_database):
    job = _job()
    Application.create(job=job, status="submitted", applied_at=None)
    register_application(job.id, CONFIG)
    assert Application.get(Application.job == job).applied_at is None


def test_an_existing_applied_at_is_kept(temporary_database):
    job = _job()
    Application.create(job=job, status="submitted", applied_at=AUGUST_1)
    register_application(job.id, CONFIG, RegisterRequest(applied_at=SEPTEMBER_1))
    assert Application.get(Application.job == job).applied_at == AUGUST_1


def test_a_draft_takes_the_requested_status_and_date(temporary_database):
    job = _job()
    Application.create(job=job, status="draft")
    result = register_application(
        job.id, CONFIG, RegisterRequest(status="screening", applied_at=NOVEMBER_1)
    )
    application = Application.get(Application.job == job)
    assert (result.status, application.applied_at) == ("screening", NOVEMBER_1)


def test_the_flag_is_set_and_cleared_through_register(temporary_database):
    job = _job()
    register_application(job.id, CONFIG, RegisterRequest(reply_mailbox_unswept=True))
    assert Application.get(Application.job == job).reply_mailbox_unswept is True
    register_application(job.id, CONFIG, RegisterRequest(reply_mailbox_unswept=False))
    assert Application.get(Application.job == job).reply_mailbox_unswept is False
    register_application(job.id, CONFIG)  # None leaves it as it is
    assert Application.get(Application.job == job).reply_mailbox_unswept is False


def test_an_invalid_status_writes_nothing(temporary_database):
    job = _job()
    result = register_application(job.id, CONFIG, RegisterRequest(status="hired"))
    assert result.kind is RegisterKind.INVALID_STATUS
    assert result.error == (
        "Invalid status 'hired'. Accepted: submitted, screening, interviews, offer, rejected, "
        "no_response."
    )
    assert Application.select().count() == 0
