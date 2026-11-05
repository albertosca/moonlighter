"""add_job fills what is missing from the ATS API or the page itself."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.core.web.posting import FetchedPosting
from moonlighter.discovery.manual_jobs import add_job

from tests.discovery.scan_fakes import CONFIG, PROFILE, evaluation_result


def _http_client(status_code=200, text="<p>Job description here</p>"):
    """Builds a mocked AsyncClient that works as an async context manager."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=status_code, text=text))
    acm = MagicMock()
    acm.__aenter__ = AsyncMock(return_value=client)
    acm.__aexit__ = AsyncMock(return_value=False)
    return acm, client


async def test_add_job_fetches_description_when_empty(temporary_database):
    init_db()
    acm, _ = _http_client(text="<html><body>Real desc</body></html>")
    with (
        patch("moonlighter.core.web.posting.httpx.AsyncClient", return_value=acm),
        patch(
            "moonlighter.discovery.manual_jobs.evaluate_job",
            new=AsyncMock(return_value=evaluation_result(8.0)),
        ),
    ):
        result = await add_job(
            "https://x.com/2", "Stripe", "Engineer", "", CONFIG, PROFILE, MagicMock()
        )
    assert "NEW" in result
    job = Job.get(Job.url == "https://x.com/2")
    assert "Real desc" in (job.description or "")


async def test_add_job_routes_through_ats_when_fields_missing(temporary_database):
    init_db()
    posting = FetchedPosting(
        company="GitLab", title="Account Executive", description="Build things."
    )
    url = "https://boards.greenhouse.io/gitlab/jobs/8503792002"
    with (
        patch(
            "moonlighter.discovery.manual_jobs.fetch_posting_via_ats",
            new=AsyncMock(return_value=posting),
        ),
        patch(
            "moonlighter.discovery.manual_jobs.evaluate_job",
            new=AsyncMock(return_value=evaluation_result(8.0)),
        ),
    ):
        result = await add_job(url, "", "", "", CONFIG, PROFILE, MagicMock())
    assert "NEW" in result
    job = Job.get(Job.url == url)
    assert job.company == "GitLab"
    assert job.title == "Account Executive"
    assert job.description == "Build things."


async def test_add_job_hands_the_ats_location_to_the_evaluator(temporary_database):
    """Without the structured location the LLM judges eligibility from the text alone —
    the 2026-08-21 gitlab false-positive class, reintroduced by any caller that omits it.
    """
    init_db()
    posting = FetchedPosting(
        company="GitLab",
        title="Account Executive",
        description="Build things.",
        location="Bangalore, India",
    )
    url = "https://boards.greenhouse.io/gitlab/jobs/8503792003"
    eval_mock = AsyncMock(return_value=evaluation_result(8.0))
    with (
        patch(
            "moonlighter.discovery.manual_jobs.fetch_posting_via_ats",
            new=AsyncMock(return_value=posting),
        ),
        patch("moonlighter.discovery.manual_jobs.evaluate_job", new=eval_mock),
    ):
        await add_job(url, "", "", "", CONFIG, PROFILE, MagicMock())
    assert eval_mock.call_args.kwargs["location"] == "Bangalore, India"
    assert eval_mock.call_args.kwargs["remote_type"] is None
    job = Job.get(Job.url == url)
    assert job.location == "Bangalore, India"


async def test_add_job_takes_the_ats_location_even_when_every_field_was_given(
    temporary_database,
):
    """With company, title and description all pasted, the ATS lookup used to be
    skipped, and the evaluator ran with no location — the gap this branch closes.
    """
    init_db()
    posting = FetchedPosting(
        company="GitLab", title="Engineer", description="API text.", location="Bangalore, India"
    )
    url = "https://boards.greenhouse.io/gitlab/jobs/8503792004"
    eval_mock = AsyncMock(return_value=evaluation_result(8.0))
    with (
        patch(
            "moonlighter.discovery.manual_jobs.fetch_posting_via_ats",
            new=AsyncMock(return_value=posting),
        ),
        patch("moonlighter.discovery.manual_jobs.evaluate_job", new=eval_mock),
    ):
        await add_job(url, "GitLab", "Engineer", "Pasted text.", CONFIG, PROFILE, MagicMock())
    assert eval_mock.call_args.kwargs["location"] == "Bangalore, India"
    # What the person pasted still wins over the API's copy.
    assert eval_mock.call_args.kwargs["description"] == "Pasted text."


async def test_add_job_marks_a_remote_ats_posting_remote(temporary_database):
    init_db()
    posting = FetchedPosting(
        company="Channable",
        title="Backend Engineer",
        description="Elixir.",
        location="Utrecht",
        remote=True,
    )
    eval_mock = AsyncMock(return_value=evaluation_result(8.0))
    with (
        patch(
            "moonlighter.discovery.manual_jobs.fetch_posting_via_ats",
            new=AsyncMock(return_value=posting),
        ),
        patch("moonlighter.discovery.manual_jobs.evaluate_job", new=eval_mock),
    ):
        await add_job(
            "https://jobs.channable.com/o/backend", "", "", "", CONFIG, PROFILE, MagicMock()
        )
    assert eval_mock.call_args.kwargs["remote_type"] == "remote"


async def test_add_job_http_non_200_returns_error(temporary_database):
    init_db()
    acm, _ = _http_client(status_code=404)
    with patch("moonlighter.core.web.posting.httpx.AsyncClient", return_value=acm):
        result = await add_job(
            "https://x.com/3", "Stripe", "Engineer", "", CONFIG, PROFILE, MagicMock()
        )
    assert "404" in result


async def test_add_job_http_exception_returns_error(temporary_database):
    init_db()
    acm = MagicMock()
    acm.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
    acm.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.core.web.posting.httpx.AsyncClient", return_value=acm):
        result = await add_job(
            "https://x.com/4", "Stripe", "Engineer", "", CONFIG, PROFILE, MagicMock()
        )
    assert "Error fetching URL" in result
