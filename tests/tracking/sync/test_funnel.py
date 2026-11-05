"""Advancing an application through the funnel: the type-to-status map, ranks and the job sync."""

from moonlighter.core.db import Job
from moonlighter.tracking.sync.funnel import _TYPE_TO_STATUS, _status_rank, advance_application


def test_an_acknowledgement_maps_to_no_status_change():
    # Absence here is the behaviour, so it gets a test — otherwise someone "completes"
    # the dict later and receipts start advancing applications again.
    assert "acknowledgement" not in _TYPE_TO_STATUS
    assert _TYPE_TO_STATUS.get("acknowledgement") is None


def test_status_rank_unknown_returns_minus_one():
    assert _status_rank("status_inexistente") == -1


def test_advance_application_syncs_job_status(temporary_database, application_factory):
    """An email-classified advance (e.g. screening) must pull Job.status to
    'applied' — the 2026-08-21 triage found jobs still 'new' with live
    applications, and sync_email_responses was one of the writers that never
    told the Job.
    """
    application = application_factory(status="submitted")
    job = application.job
    job.status = "new"  # simulate the drift seen live
    job.save()

    advance_application(
        application,
        {"type": "interview_invite", "summary": "let's chat"},
        "ref",
        stages=["Screening"],
    )
    assert Job.get_by_id(job.id).status == "applied"
