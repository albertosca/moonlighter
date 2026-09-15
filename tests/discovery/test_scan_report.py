import pytest
from moonlighter.core.db import Job, init_db
from moonlighter.discovery.service import _format_report


@pytest.fixture
def three_jobs(tmp_db):
    init_db()
    return [
        Job.create(source="greenhouse", company="Acme", title="Staff Engineer",
                   url="https://boards.greenhouse.io/acme/jobs/1", score=9.0, status="new"),
        Job.create(source="greenhouse", company="Acme", title="Intern",
                   url="https://boards.greenhouse.io/acme/jobs/2", score=2.0, status="rejected"),
        Job.create(source="greenhouse", company="Acme", title="Recruiter",
                   url="https://boards.greenhouse.io/acme/jobs/3", score=0.0,
                   status="rejected", score_notes="title filtered: recruiter"),
    ]


def test_format_report_above_threshold_is_unchanged(three_jobs, snapshot_text):
    snapshot_text(_format_report(three_jobs, spend_hit=False, threshold=7.0), "above_threshold")


def test_format_report_none_above_threshold_is_unchanged(three_jobs, snapshot_text):
    snapshot_text(_format_report(three_jobs[1:], spend_hit=False, threshold=7.0), "none_above")


def test_format_report_spend_hit_is_unchanged(three_jobs, snapshot_text):
    snapshot_text(_format_report(three_jobs, spend_hit=True, threshold=7.0), "spend_hit")
