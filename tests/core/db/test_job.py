"""The Job model stores its salary and nullable columns, defaults status to "new", keeps url unique, decodes caveats and records its timestamps."""

import json
from datetime import datetime, timedelta

import pytest
from peewee import IntegrityError

from moonlighter.core.db import Job, init_db
from tests.core.db.sample_job import make_job


def test_job_salary_fields(temporary_database):
    init_db()
    job = make_job(
        salary_min=150000,
        salary_max=200000,
        salary_currency="USD",
        salary_source="stated",
    )
    saved = Job.get_by_id(job.id)
    assert saved.salary_min == 150000
    assert saved.salary_max == 200000
    assert saved.salary_currency == "USD"
    assert saved.salary_source == "stated"


def test_job_salary_notes_field(temporary_database):
    """Job.salary_notes is stored and retrievable."""
    init_db()
    job = make_job(salary_notes="Based on Glassdoor and Levels.fyi estimates.")
    saved = Job.get_by_id(job.id)
    assert "Glassdoor" in saved.salary_notes


def test_job_nullable_fields_default_none(temporary_database):
    init_db()
    job = make_job()
    saved = Job.get_by_id(job.id)
    assert saved.location is None
    assert saved.remote_type is None
    assert saved.posted_at is None
    assert saved.score is None


def test_job_status_default(temporary_database):
    init_db()
    job = make_job()
    assert job.status == "new"


def test_job_url_unique_raises(temporary_database):
    init_db()
    make_job(url="https://example.com/job/dup")
    with pytest.raises(IntegrityError):
        make_job(url="https://example.com/job/dup")


def test_job_get_caveats_valid_json(temporary_database):
    init_db()
    job = make_job(caveats='["US only", "requires relocation"]')
    assert job.get_caveats() == ["US only", "requires relocation"]


def test_job_get_caveats_empty_string(temporary_database):
    init_db()
    job = make_job(caveats="")
    assert job.get_caveats() == []


def test_job_get_caveats_null(temporary_database):
    init_db()
    job = make_job()  # caveats not set → None
    assert job.get_caveats() == []


def test_job_get_caveats_invalid_json(temporary_database):
    init_db()
    job = make_job(caveats="not json")
    with pytest.raises(json.JSONDecodeError):
        job.get_caveats()


def test_job_found_at_is_recent(temporary_database):
    init_db()
    before = datetime.now()  # noqa: DTZ005 - the database stores naive local time
    job = make_job()
    after = datetime.now()  # noqa: DTZ005 - the database stores naive local time
    assert before - timedelta(seconds=5) <= job.found_at <= after + timedelta(seconds=5)


def test_job_posted_at_nullable(temporary_database):
    init_db()
    job = make_job(posted_at=None)
    results = list(Job.select().where(Job.posted_at.is_null(is_null=True)))
    assert any(result.id == job.id for result in results)


def test_job_closed_at_is_null_by_default(temporary_database):
    init_db()
    job = make_job()
    assert job.closed_at is None


def test_job_closed_at_stored_and_retrieved(temporary_database):
    init_db()
    when = datetime(2026, 7, 1, 12, 0, 0)  # noqa: DTZ001 - the database stores naive local time
    job = make_job(status="archived", closed_at=when)
    saved = Job.get_by_id(job.id)
    assert saved.status == "archived"
    assert saved.closed_at == when
