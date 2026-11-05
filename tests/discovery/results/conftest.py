"""Fixtures for the scan-report tests."""

import pytest
from moonlighter.core.db import Job, init_db


@pytest.fixture
def three_jobs(temporary_database):
    init_db()
    return [
        Job.create(
            source="greenhouse",
            company="Acme",
            title="Staff Engineer",
            url="https://boards.greenhouse.io/acme/jobs/1",
            score=9.0,
            status="new",
        ),
        Job.create(
            source="greenhouse",
            company="Acme",
            title="Intern",
            url="https://boards.greenhouse.io/acme/jobs/2",
            score=2.0,
            status="rejected",
        ),
        Job.create(
            source="greenhouse",
            company="Acme",
            title="Recruiter",
            url="https://boards.greenhouse.io/acme/jobs/3",
            score=0.0,
            status="rejected",
            score_notes="title filtered: recruiter",
        ),
    ]
