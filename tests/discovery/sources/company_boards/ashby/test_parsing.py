"""How an Ashby posting becomes a job: the REST endpoint, fields, remote flag, dates and skipped postings."""

from datetime import datetime
from unittest.mock import patch

from moonlighter.discovery.sources.company_boards.ashby import AshbyScanner
from tests.discovery.sources.company_boards.ashby.fake_board import ASHBY_JOB, ashby_response
from tests.discovery.sources.fake_http_clients import make_mock_client


async def test_ashby_scan_success():
    mock_client = make_mock_client(ashby_response(ASHBY_JOB))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["openai"])
    assert len(jobs) == 1
    assert jobs[0].company == "openai"
    assert jobs[0].title == "ML Engineer"
    assert jobs[0].source == "ashby"
    assert jobs[0].url == "https://jobs.ashbyhq.com/openai/d3bc1ced"
    assert "language models" in jobs[0].description


async def test_ashby_uses_the_rest_board_endpoint():
    """Guards the regression directly: a POST to the retired GraphQL endpoint is
    what made every company look empty.
    """
    mock_client = make_mock_client(ashby_response(ASHBY_JOB))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        await AshbyScanner().scan(["openai"])
    mock_client.post.assert_not_called()
    url = mock_client.get.call_args.args[0]
    assert url == "https://api.ashbyhq.com/posting-api/job-board/openai"


async def test_ashby_is_remote_flag_true():
    mock_client = make_mock_client(ashby_response(ASHBY_JOB))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["openai"])
    assert jobs[0].remote_type == "remote"


async def test_ashby_is_remote_flag_false_uses_location():
    job = {**ASHBY_JOB, "location": "São Paulo, Brazil", "isRemote": False}
    mock_client = make_mock_client(ashby_response(job))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs[0].remote_type is None  # bare city: unknown, never invented onsite


async def test_ashby_unlisted_job_is_skipped():
    """isListed=False means the posting is not public — surfacing it would send the
    candidate to a page that is not accepting applications.
    """
    job = {**ASHBY_JOB, "isListed": False}
    mock_client = make_mock_client(ashby_response(job))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_missing_published_at_returns_none():
    job = {
        field_name: field_value
        for field_name, field_value in ASHBY_JOB.items()
        if field_name != "publishedAt"
    }
    mock_client = make_mock_client(ashby_response(job))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert len(jobs) == 1
    assert jobs[0].posted_at is None


async def test_ashby_published_at_parsed_as_datetime():
    """The live API returns a timezone-aware ISO timestamp, not a bare date."""
    mock_client = make_mock_client(ashby_response(ASHBY_JOB))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["openai"])
    assert isinstance(jobs[0].posted_at, datetime)


async def test_ashby_unparseable_published_at_returns_none():
    job = {**ASHBY_JOB, "publishedAt": "not-a-date"}
    mock_client = make_mock_client(ashby_response(job))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs[0].posted_at is None


async def test_ashby_missing_title_skips_job():
    job = {
        field_name: field_value
        for field_name, field_value in ASHBY_JOB.items()
        if field_name != "title"
    }
    mock_client = make_mock_client(ashby_response(job))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_missing_url_skips_job():
    job = {
        field_name: field_value
        for field_name, field_value in ASHBY_JOB.items()
        if field_name != "jobUrl"
    }
    mock_client = make_mock_client(ashby_response(job))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []
