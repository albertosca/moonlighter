"""The fuzzy company-and-title matcher, which must never pick one of several matches."""

from moonlighter.core.db import init_db
from moonlighter.tracking.sync.application_matching import _match_by_company_title

from tests.tracking.pipeline_rows import make_application, make_job


class TestMatchByCompanyTitle:
    """Direct unit tests for the fuzzy company+title matcher. It only ever
    feeds a 'fuzzy' suggestion (never an auto-mutation — see S-06 tests in
    TestSyncResponses), so the safety property under test here is: ambiguity
    must yield None, never a silently-picked wrong Application.
    """

    def test_exact_single_match_returns_application(self, temporary_database):
        init_db()
        job = make_job(temporary_database, company="Anthropic", title="Senior Engineer")
        application = make_application(job, status="submitted")

        result = _match_by_company_title("Anthropic", "Senior Engineer")
        assert result is not None
        assert result.id == application.id

    def test_no_match_returns_none(self, temporary_database):
        init_db()
        job = make_job(temporary_database, company="Anthropic", title="Senior Engineer")
        make_application(job, status="submitted")

        assert _match_by_company_title("Totally Unrelated Co", "Some Other Role") is None

    def test_ambiguous_match_returns_none_not_a_silent_pick(self, temporary_database):
        """Two active applications with the same company+title: the matcher
        must refuse to guess — returning None is the safe behavior, since
        picking either one at random would risk mutating the WRONG
        application's status/notes.
        """
        init_db()
        job1 = make_job(
            temporary_database, company="Stripe", title="Engineer", url="https://x.com/a"
        )
        job2 = make_job(
            temporary_database, company="Stripe", title="Engineer", url="https://x.com/b"
        )
        make_application(job1, status="submitted")
        make_application(job2, status="screening")

        assert _match_by_company_title("Stripe", "Engineer") is None

    def test_both_none_returns_none_without_querying(self, temporary_database):
        init_db()
        job = make_job(temporary_database, company="Anthropic", title="Senior Engineer")
        make_application(job, status="submitted")

        assert _match_by_company_title(None, None) is None

    def test_case_insensitive_company_match(self, temporary_database):
        init_db()
        job = make_job(temporary_database, company="Anthropic", title="Senior Engineer")
        application = make_application(job, status="submitted")

        result = _match_by_company_title("ANTHROPIC", "senior engineer")
        assert result is not None
        assert result.id == application.id

    def test_partial_substring_match(self, temporary_database):
        """Matching uses LIKE %term% — a partial title still matches."""
        init_db()
        job = make_job(temporary_database, company="Anthropic", title="Senior Backend Engineer")
        application = make_application(job, status="submitted")

        result = _match_by_company_title("Anthropic", "Backend")
        assert result is not None
        assert result.id == application.id

    def test_only_company_given_filters_by_company_alone(self, temporary_database):
        init_db()
        job = make_job(temporary_database, company="Anthropic", title="Senior Engineer")
        application = make_application(job, status="submitted")

        result = _match_by_company_title("Anthropic", None)
        assert result is not None
        assert result.id == application.id

    def test_only_title_given_filters_by_title_alone(self, temporary_database):
        init_db()
        job = make_job(temporary_database, company="Anthropic", title="Staff Platform Engineer")
        application = make_application(job, status="submitted")

        result = _match_by_company_title(None, "Platform Engineer")
        assert result is not None
        assert result.id == application.id

    def test_inactive_status_applications_are_excluded(self, temporary_database):
        """A 'rejected' or 'draft' Application must never surface as a fuzzy
        match target — only _ACTIVE_STATUSES are eligible, so a stale/closed
        application can't get reopened by a coincidental company+title hit.
        """
        init_db()
        job = make_job(temporary_database, company="Anthropic", title="Senior Engineer")
        make_application(job, status="rejected")
        make_application(job, status="draft")

        assert _match_by_company_title("Anthropic", "Senior Engineer") is None

    def test_active_match_found_even_with_an_inactive_duplicate(self, temporary_database):
        """A rejected duplicate for the same company+title must not make an
        otherwise-unique active match look ambiguous.
        """
        init_db()
        job = make_job(temporary_database, company="Anthropic", title="Senior Engineer")
        make_application(job, status="rejected")
        active_app = make_application(job, status="submitted")

        result = _match_by_company_title("Anthropic", "Senior Engineer")
        assert result is not None
        assert result.id == active_app.id

    def test_company_filter_alone_is_ambiguous_across_two_titles(self, temporary_database):
        """Same company, two different active roles, no job_title given to
        disambiguate → None, not an arbitrary pick.
        """
        init_db()
        job1 = make_job(
            temporary_database, company="Anthropic", title="Backend Engineer", url="https://x/1"
        )
        job2 = make_job(
            temporary_database, company="Anthropic", title="Frontend Engineer", url="https://x/2"
        )
        make_application(job1, status="submitted")
        make_application(job2, status="submitted")

        assert _match_by_company_title("Anthropic", None) is None
