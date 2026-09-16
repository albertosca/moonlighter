from moonlighter.core.db import Application, Job, init_db

CONFIG = {"email": {"address": "jane@example.com"}}


def _job():
    init_db()
    return Job.create(
        source="greenhouse", company="Acme", title="Eng", url="https://x/1", status="new"
    )


def test_register_creates_a_submitted_application_with_a_tracking_ref(tmp_db):
    from moonlighter.tracking.register import RegisterKind, register_application, register_to_dict

    job = _job()
    r = register_application(job.id, CONFIG)
    app = Application.get(Application.job == job)
    assert r.kind is RegisterKind.REGISTERED
    assert (r.application_id, r.status) == (app.id, "submitted")
    assert app.applied_at is not None
    assert r.email_ref == app.email_ref and len(r.email_ref) == 8
    assert r.alias == f"jane+{r.email_ref}@example.com"
    assert (
        Job.get_by_id(job.id).status == "applied"
    )  # sync_job_status ran: app "submitted" -> job "applied"
    assert register_to_dict(r)["kind"] == "registered"


def test_register_promotes_an_existing_draft_and_keeps_its_ref(tmp_db):
    from moonlighter.tracking.register import register_application

    job = _job()
    Application.create(job=job, status="draft", email_ref="ab12cd34")
    r = register_application(job.id, CONFIG)
    assert (r.status, r.email_ref) == ("submitted", "ab12cd34")


def test_register_leaves_an_already_advanced_application_alone(tmp_db):
    from moonlighter.tracking.register import register_application

    job = _job()
    Application.create(job=job, status="interviews", email_ref="ab12cd34")
    r = register_application(job.id, CONFIG)
    assert r.status == "interviews"


def test_register_without_a_configured_address_has_no_alias(tmp_db):
    from moonlighter.tracking.register import RegisterKind, register_application

    job = _job()
    r = register_application(job.id, {})
    assert r.kind is RegisterKind.REGISTERED
    assert r.alias is None and r.email_ref is not None


def test_register_unknown_job(tmp_db):
    from moonlighter.tracking.register import RegisterKind, register_application, register_to_dict

    init_db()
    r = register_application(4242, CONFIG)
    assert r.kind is RegisterKind.JOB_NOT_FOUND
    assert register_to_dict(r) == {
        "kind": "job_not_found",
        "job_id": 4242,
        "application_id": None,
        "status": None,
        "email_ref": None,
        "alias": None,
        "error": "Job 4242 not found.",
    }
