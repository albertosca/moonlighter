"""Pins the three writes of reevaluation_records: what each stores and which columns it leaves alone."""

import json

import pytest
import reevaluation_records

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.evaluation.models import EvaluationResult
from tests.scripts.reevaluate_bug_victims.harness import UNTOUCHED_NOTES, victim


@pytest.fixture(autouse=True)
def _database(temporary_database):
    init_db()


def _stored(job: Job) -> tuple:
    row = Job.get_by_id(job.id)
    return (row.score, row.score_notes, row.caveats, row.status)


def test_a_title_skip_archives_with_a_zero_score_and_names_the_pattern():
    job = victim("Acme", "Recruiter", score=4.0, status="new", caveats="old")

    reevaluation_records.record_title_skip(job.id, "recruiter")

    assert _stored(job) == (0.0, "title filtered: 'recruiter'", "[]", "archived")


def test_an_error_changes_only_the_notes_and_keeps_the_first_200_characters():
    job = victim("Acme", "Dev", caveats="old")

    reevaluation_records.record_error(job.id, RuntimeError("x" * 300))

    assert _stored(job) == (0, "reevaluate_error: " + "x" * 200, "old", "archived")


def test_a_result_stores_the_eight_fields_and_the_given_status():
    job = victim("Acme", "Dev")
    result = EvaluationResult(
        score=7.0,
        score_notes="fits",
        caveats=["c1", "c2"],
        salary_min=100,
        salary_max=200,
        salary_currency="USD",
        salary_source="stated",
    )

    reevaluation_records.record_result(job.id, result, "new")

    row = Job.get_by_id(job.id)
    assert (row.score, row.score_notes, json.loads(row.caveats), row.status) == (
        7.0,
        "fits",
        ["c1", "c2"],
        "new",
    )
    assert (row.salary_min, row.salary_max, row.salary_currency, row.salary_source) == (
        100,
        200,
        "USD",
        "stated",
    )


def test_a_write_touches_only_its_own_job():
    target = victim("Acme", "Target")
    bystander = victim("Acme", "Bystander")

    reevaluation_records.record_title_skip(target.id, "x")
    reevaluation_records.record_error(target.id, RuntimeError("e"))

    assert Job.get_by_id(bystander.id).score_notes == UNTOUCHED_NOTES
