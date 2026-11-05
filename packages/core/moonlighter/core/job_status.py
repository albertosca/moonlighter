"""Keeps Job.status in step with its Application, for every writer of Application.status."""

from moonlighter.core.db import Application

_APP_TO_JOB_STATUS = {
    "submitted": "applied",
    "screening": "applied",
    "interviews": "applied",
    "offer": "applied",
    "rejected": "rejected",
}


def sync_job_status(application: Application) -> None:
    """Pulls Job.status along whenever Application.status changes.

    Provenance: 2026-08-21 manual triage — 5 jobs still 'new' while their
    Application was already submitted/rejected, nearly offering a duplicate
    application twice in one session. Every Application.status writer calls
    this after saving; 'draft' maps to nothing (a draft is not yet an
    application the queue should hide).
    """
    target = _APP_TO_JOB_STATUS.get(str(application.status))
    if target is None:
        return
    job = application.job
    if job.status != target:
        job.status = target
        job.save()
