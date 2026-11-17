"""make_application: a job and its application, silent for N days, after a year-long sweep."""

from datetime import timedelta

import pytest

from moonlighter.core.db import Application, EmailSyncRun, Job, init_db
from tests.discovery.unanswered.clock import NOW, ONE_YEAR_AGO


@pytest.fixture
def make_application(temporary_database):
    init_db()
    EmailSyncRun.create(finished_at=NOW - timedelta(days=1), window_start=ONE_YEAR_AGO)
    count = 0

    def _make(days_silent, status="submitted", notes=None, **fields):
        nonlocal count
        count += 1
        job = Job.create(
            source="manual",
            company=f"Company{count}",
            title="Eng",
            url=f"https://x/{count}",
            status="applied",
        )
        return Application.create(
            job=job,
            status=status,
            notes=notes,
            updated_at=NOW - timedelta(days=days_silent),
            **fields,
        )

    return _make
