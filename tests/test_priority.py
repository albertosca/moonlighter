"""Rejection-aware queue ordering, computed at read time.

Provenance: 2026-08-24 (Alberto) — Holepunch #3197 was offered without anyone
knowing the same company rejected #3200 eight days earlier; the information
was in the DB and nothing surfaced it. The persisted score stays untouched:
the penalty is derived on read (so it decays as rejections age with no
re-scoring), reorders toward the end, and never hides a job.
"""

import datetime

from moonlighter.core.db import Application, Job, init_db
from moonlighter.priority import (
    REJECTION_WINDOW_DAYS,
    company_rejection_ages,
    rejection_badge,
    rejection_penalty,
)

NOW = datetime.datetime(2026, 8, 24, 12, 0, 0)


class TestPenalty:
    def test_one_fresh_rejection_weighs_close_to_one(self):
        assert rejection_penalty([0.0]) == 1.0

    def test_a_rejection_beyond_the_window_weighs_nothing(self):
        assert rejection_penalty([REJECTION_WINDOW_DAYS + 1.0]) == 0.0

    def test_two_rejections_weigh_more_than_one(self):
        assert rejection_penalty([8.0, 8.0]) > rejection_penalty([8.0])

    def test_decays_with_age(self):
        assert rejection_penalty([80.0]) < rejection_penalty([8.0])

    def test_no_rejections_no_penalty(self):
        assert rejection_penalty([]) == 0.0


class TestBadge:
    def test_names_count_and_recency(self):
        assert rejection_badge([8.0, 30.0]) == "⚠ rejected 2x, last 8d ago"

    def test_none_without_history(self):
        assert rejection_badge([]) is None

    def test_only_window_rejections_count(self):
        assert rejection_badge([REJECTION_WINDOW_DAYS + 1.0]) is None


def _rejected_pair(company, days_ago, url):
    job = Job.create(source="greenhouse", company=company, title="Eng", url=url, status="rejected")
    Application.create(
        job=job, status="rejected", updated_at=NOW - datetime.timedelta(days=days_ago)
    )
    return job


class TestCompanyAges:
    def test_collects_ages_case_insensitively(self, tmp_db):
        # The live case: 'Holepunch' on one row, 'holepunch' on another.
        init_db()
        _rejected_pair("Holepunch", 8, "https://x.com/rej/1")
        ages = company_rejection_ages(now=NOW)
        assert ages["holepunch"] == [8.0]

    def test_ignores_non_rejected_applications(self, tmp_db):
        init_db()
        job = Job.create(
            source="greenhouse", company="acme", title="Eng", url="https://x.com/rej/2"
        )
        Application.create(job=job, status="submitted", updated_at=NOW)
        assert "acme" not in company_rejection_ages(now=NOW)
