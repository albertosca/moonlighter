"""sync_job_status moves Job.status to "applied" or "rejected" as its Application advances, and leaves it alone for a draft."""

import os

from moonlighter.core.db import Application, Job, init_db, sync_job_status
from tests.core.db.sample_job import make_job

# ── sync_job_status ──────────────────────────────────────────────────────────
# Provenance: 2026-08-21 manual triage — 5 jobs still 'new' while their
# Application was already submitted/rejected; a duplicate application was
# nearly offered twice in one session. Every Application.status writer calls
# this helper so Job.status can never drift again.


def _sync_pair(temporary_database, app_status):
    os.environ["MOONLIGHTER_DB_PATH"] = temporary_database
    init_db()
    job = make_job(status="new")
    app = Application.create(job=job, status=app_status)
    return job, app


def test_sync_job_status_submitted_marks_job_applied(temporary_database):
    job, app = _sync_pair(temporary_database, "submitted")
    sync_job_status(app)
    assert Job.get_by_id(job.id).status == "applied"


def test_sync_job_status_rejected_marks_job_rejected(temporary_database):
    job, app = _sync_pair(temporary_database, "rejected")
    sync_job_status(app)
    assert Job.get_by_id(job.id).status == "rejected"


def test_sync_job_status_interview_stages_mark_job_applied(temporary_database):
    job, app = _sync_pair(temporary_database, "interviews")
    sync_job_status(app)
    assert Job.get_by_id(job.id).status == "applied"


def test_sync_job_status_draft_leaves_job_alone(temporary_database):
    job, app = _sync_pair(temporary_database, "draft")
    sync_job_status(app)
    assert Job.get_by_id(job.id).status == "new"
