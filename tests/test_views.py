from datetime import datetime

from moonlighter.core.db import Job, init_db
from moonlighter.views import render_jobs_table


def _job(temporary_database, **overrides):
    defaults = {
        "source": "greenhouse",
        "company": "Stripe",
        "title": "Engineer",
        "url": "https://x.com/1",
        "score": 8.0,
        "status": "new",
    }
    defaults.update(overrides)
    return Job.create(**defaults)


def test_render_includes_company_and_title(temporary_database):
    init_db()
    _job(temporary_database)
    out = render_jobs_table([Job.get(Job.url == "https://x.com/1")])
    assert "Stripe" in out
    assert "Engineer" in out


def test_render_salary_estimate_marks_asterisk(temporary_database):
    init_db()
    _job(temporary_database, salary_min=150000, salary_max=200000, salary_source="llm_estimate")
    out = render_jobs_table([Job.get(Job.url == "https://x.com/1")])
    assert " *" in out


def test_render_salary_min_only_shows_plus(temporary_database):
    init_db()
    _job(temporary_database, url="https://x.com/2", salary_min=120000, salary_max=None)
    out = render_jobs_table([Job.get(Job.url == "https://x.com/2")])
    assert "k+" in out


def test_render_handles_null_score_and_no_salary(temporary_database):
    init_db()
    _job(
        temporary_database,
        url="https://x.com/3",
        score=None,
        posted_at=datetime(2026, 6, 1),  # noqa: DTZ001 - the database stores naive local time
    )
    out = render_jobs_table([Job.get(Job.url == "https://x.com/3")])
    assert "—" in out  # null score becomes an em dash
    assert "Jun 01" in out
