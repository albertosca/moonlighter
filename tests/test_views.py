import datetime

from gauntler.core.db import Job, init_db
from gauntler.views import render_jobs_table


def _job(tmp_db, **kwargs):
    defaults = {
        "source": "greenhouse",
        "company": "Stripe",
        "title": "Engineer",
        "url": "https://x.com/1",
        "score": 8.0,
        "status": "new",
    }
    defaults.update(kwargs)
    return Job.create(**defaults)


def test_render_includes_company_and_title(tmp_db):
    init_db()
    _job(tmp_db)
    out = render_jobs_table([Job.get(Job.url == "https://x.com/1")])
    assert "Stripe" in out
    assert "Engineer" in out


def test_render_salary_estimate_marks_asterisk(tmp_db):
    init_db()
    _job(tmp_db, salary_min=150000, salary_max=200000, salary_source="llm_estimate")
    out = render_jobs_table([Job.get(Job.url == "https://x.com/1")])
    assert " *" in out


def test_render_salary_min_only_shows_plus(tmp_db):
    init_db()
    _job(tmp_db, url="https://x.com/2", salary_min=120000, salary_max=None)
    out = render_jobs_table([Job.get(Job.url == "https://x.com/2")])
    assert "k+" in out


def test_render_handles_null_score_and_no_salary(tmp_db):
    init_db()
    _job(tmp_db, url="https://x.com/3", score=None, posted_at=datetime.datetime(2026, 6, 1))
    out = render_jobs_table([Job.get(Job.url == "https://x.com/3")])
    assert "—" in out  # score nulo vira travessão
    assert "01/06" in out
