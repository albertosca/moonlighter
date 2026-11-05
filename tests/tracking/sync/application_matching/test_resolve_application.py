"""Resolving a reply to an application: reference first, then the fuzzy match, else uncertain."""

from moonlighter.core.db import init_db
from moonlighter.tracking.sync.application_matching import resolve_application

from tests.tracking.pipeline_rows import make_application, make_job


def test_resolve_application_ref_no_match_falls_through(temporary_database):
    """A ref given but no Application → DoesNotExist swallowed, falls through to fuzzy (422-423)."""
    init_db()
    application, match = resolve_application(
        "nonexistent_ref", {"company": None, "job_title": None}
    )
    assert application is None
    assert match == "uncertain"


def test_resolve_application_fuzzy_by_title_only(temporary_database):
    """No company, only job_title → filters by title only (436->438) and matches 1 (fuzzy)."""
    init_db()
    job = make_job(temporary_database, title="Staff Backend Engineer")
    make_application(job, status="submitted")
    application, match = resolve_application(None, {"company": None, "job_title": "Staff Backend"})
    assert match == "fuzzy"
    assert application is not None


def test_resolve_application_fuzzy_by_company_only(temporary_database):
    """Only company, no job_title → filters by company only (438->441)."""
    init_db()
    job = make_job(temporary_database, company="Anthropic")
    make_application(job, status="submitted")
    application, match = resolve_application(None, {"company": "Anthropic", "job_title": None})
    assert match == "fuzzy"
    assert application is not None


def test_resolve_application_no_company_no_title_is_uncertain(temporary_database):
    """No ref, no company, and no job_title → uncertain (448)."""
    init_db()
    application, match = resolve_application(None, {"company": None, "job_title": None})
    assert application is None
    assert match == "uncertain"


def test_resolve_application_fuzzy_zero_matches_is_uncertain(temporary_database):
    """A company with no matching Application → 0 results → uncertain (444->448)."""
    init_db()
    application, match = resolve_application(
        None, {"company": "NonexistentCompany", "job_title": None}
    )
    assert application is None
    assert match == "uncertain"
