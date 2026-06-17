import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from candidatador.scanner.http_sources import AshbyScanner, GreenhouseScanner, LeverScanner

GREENHOUSE_RESPONSE = {
    "jobs": [
        {
            "id": 123,
            "title": "Senior Software Engineer",
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/123",
            "location": {"name": "Remote"},
            "updated_at": "2026-05-20T12:00:00Z",
        }
    ]
}

LEVER_RESPONSE = [
    {
        "id": "abc-123",
        "text": "Staff Engineer",
        "hostedUrl": "https://jobs.lever.co/gitlab/abc-123",
        "categories": {"location": "Remote", "commitment": "Full-time"},
        "createdAt": 1716220800000,
        "descriptionPlain": "Build distributed systems in Elixir and Go.",
    }
]


@pytest.mark.asyncio
async def test_greenhouse_scan():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = GREENHOUSE_RESPONSE
        mock_client.get = AsyncMock(return_value=mock_response)

        scanner = GreenhouseScanner()
        jobs = await scanner.scan(["stripe"])

    assert len(jobs) == 1
    assert jobs[0].company == "stripe"
    assert jobs[0].title == "Senior Software Engineer"
    assert jobs[0].remote_type == "remote"
    assert jobs[0].source == "greenhouse"


@pytest.mark.asyncio
async def test_lever_scan():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = LEVER_RESPONSE
        mock_client.get = AsyncMock(return_value=mock_response)

        scanner = LeverScanner()
        jobs = await scanner.scan(["gitlab"])

    assert len(jobs) == 1
    assert jobs[0].company == "gitlab"
    assert jobs[0].title == "Staff Engineer"
    assert jobs[0].remote_type == "remote"
    assert jobs[0].source == "lever"
    assert "Elixir" in jobs[0].description  # QUALITY-01: descrição extraída


@pytest.mark.asyncio
async def test_greenhouse_404_skips_company():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        scanner = GreenhouseScanner()
        jobs = await scanner.scan(["nonexistent-co"])

    assert jobs == []


# --- helper ---


def _make_mock_client(response_json=None, status_code=200, raise_exc=None):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = status_code
    if response_json is not None:
        mock_response.json.return_value = response_json

    if raise_exc:
        mock_client.get = AsyncMock(side_effect=raise_exc)
        mock_client.post = AsyncMock(side_effect=raise_exc)
    else:
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response)

    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# --- GreenhouseScanner new tests ---


async def test_greenhouse_html_stripped_from_description():
    response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": "2026-05-20T12:00:00Z",
                "content": "<p>Hello</p><br/>World",
            }
        ]
    }
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert len(jobs) == 1
    assert "<" not in jobs[0].description
    assert ">" not in jobs[0].description
    assert "Hello" in jobs[0].description


async def test_greenhouse_posted_at_parsed():
    response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": "2026-05-20T12:00:00Z",
            }
        ]
    }
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs[0].posted_at is not None
    assert isinstance(jobs[0].posted_at, datetime)


async def test_greenhouse_posted_at_invalid_format():
    response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": "not-a-date",
            }
        ]
    }
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs[0].posted_at is None


async def test_greenhouse_missing_location():
    response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "updated_at": "2026-05-20T12:00:00Z",
            }
        ]
    }
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs[0].location is None
    assert jobs[0].remote_type is None


async def test_greenhouse_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_empty_jobs_list():
    mock_client = _make_mock_client({"jobs": []})
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_multiple_companies():
    response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": "2026-05-20T12:00:00Z",
            }
        ]
    }
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["stripe", "linear"])
    assert len(jobs) == 2


# --- LeverScanner new tests ---


async def test_lever_skips_entry_without_title():
    response = [
        {
            "id": "1",
            "text": "",
            "hostedUrl": "https://jobs.lever.co/co/1",
            "categories": {"location": "Remote"},
            "createdAt": 1716220800000,
        }
    ]
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_skips_entry_without_url():
    response = [
        {
            "id": "1",
            "text": "Eng",
            "hostedUrl": "",
            "categories": {"location": "Remote"},
            "createdAt": 1716220800000,
        }
    ]
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_timestamp_is_utc_aware():
    response = [
        {
            "id": "1",
            "text": "Eng",
            "hostedUrl": "https://jobs.lever.co/co/1",
            "categories": {"location": "Remote"},
            "createdAt": 1716220800000,
        }
    ]
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs[0].posted_at is not None
    assert jobs[0].posted_at.tzinfo is not None


async def test_lever_missing_created_at():
    response = [
        {
            "id": "1",
            "text": "Eng",
            "hostedUrl": "https://jobs.lever.co/co/1",
            "categories": {"location": "Remote"},
        }
    ]
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs[0].posted_at is None


async def test_lever_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_500_response_skips_company():
    mock_client = _make_mock_client([], status_code=500)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_empty_array_response():
    mock_client = _make_mock_client([])
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


# --- AshbyScanner tests ---

ASHBY_RESPONSE = {
    "data": {
        "jobPostings": [
            {
                "id": "1",
                "title": "ML Engineer",
                "locationName": "Remote",
                "isRemote": True,
                "publishedDate": "2026-05-01",
                "descriptionPlain": "Train and serve large language models.",
                "jobPostingAbsoluteUrl": "https://jobs.ashbyhq.com/openai/1",
            }
        ]
    }
}


async def test_ashby_scan_success():
    mock_client = _make_mock_client(ASHBY_RESPONSE)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["openai"])
    assert len(jobs) == 1
    assert jobs[0].company == "openai"
    assert jobs[0].title == "ML Engineer"
    assert jobs[0].source == "ashby"
    assert "language models" in jobs[0].description  # QUALITY-01: descrição extraída


async def test_ashby_is_remote_flag_true():
    mock_client = _make_mock_client(ASHBY_RESPONSE)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["openai"])
    assert jobs[0].remote_type == "remote"


async def test_ashby_is_remote_flag_false_uses_location():
    response = {
        "data": {
            "jobPostings": [
                {
                    "id": "2",
                    "title": "Eng",
                    "locationName": "São Paulo, Brazil",
                    "isRemote": False,
                    "publishedDate": "2026-05-01",
                    "jobPostingAbsoluteUrl": "https://jobs.ashbyhq.com/co/2",
                }
            ]
        }
    }
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs[0].remote_type == "onsite"


async def test_ashby_500_response_skips_company():
    mock_client = _make_mock_client({}, status_code=500)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_graphql_error_returns_empty():
    """API returns {"errors": [...]} → no data key → returns []."""
    response = {"errors": [{"message": "Unauthorized"}]}
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_missing_published_date_returns_none():
    """publishedDate absent from response → posted_at is None."""
    response = {
        "data": {
            "jobPostings": [
                {
                    "id": "5",
                    "title": "Eng",
                    "locationName": "NYC",
                    "isRemote": False,
                    "jobPostingAbsoluteUrl": "https://jobs.ashbyhq.com/co/5",
                }
            ]
        }
    }
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert len(jobs) == 1
    assert jobs[0].posted_at is None


async def test_ashby_published_date_parsed_as_datetime():
    """publishedDate '2026-05-01' is parsed into a datetime object."""
    response = {
        "data": {
            "jobPostings": [
                {
                    "id": "6",
                    "title": "Eng",
                    "locationName": "Remote",
                    "isRemote": True,
                    "publishedDate": "2026-05-01",
                    "jobPostingAbsoluteUrl": "https://jobs.ashbyhq.com/co/6",
                }
            ]
        }
    }
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs[0].posted_at is not None
    assert isinstance(jobs[0].posted_at, datetime)


async def test_ashby_empty_job_postings_returns_empty():
    """jobPostings: [] → scan returns []."""
    response = {"data": {"jobPostings": []}}
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_partial_failure_continues():
    """1 of 3 companies returns 500; the other 2 succeed → jobs from 2 companies returned."""
    success_response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "absolute_url": "https://boards.greenhouse.io/ok/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": "2026-05-20T12:00:00Z",
            }
        ]
    }
    call_count = [0]

    async def get_with_partial_failure(url, **kwargs):
        call_count[0] += 1
        resp = MagicMock()
        if call_count[0] == 2:
            resp.status_code = 500
        else:
            resp.status_code = 200
            resp.json.return_value = success_response
        return resp

    mock_client = MagicMock()
    mock_client.get = get_with_partial_failure
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["ok1", "fail", "ok2"])
    assert len(jobs) == 2


async def test_lever_multiple_companies_returns_all():
    """2 Lever companies each with 1 job → 2 jobs total."""
    response = [
        {
            "id": "1",
            "text": "Eng",
            "hostedUrl": "https://jobs.lever.co/co/1",
            "categories": {"location": "Remote"},
            "createdAt": 1716220800000,
        }
    ]
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["stripe", "linear"])
    assert len(jobs) == 2
    assert jobs[0].company == "stripe"
    assert jobs[1].company == "linear"


# ── Greenhouse: validação de schema ───────────────────────────────────────────


async def test_greenhouse_missing_title_skips_job():
    """Item sem 'title' é ignorado — não gera KeyError."""
    response = {
        "jobs": [
            {
                "id": 1,
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": "2026-05-20T12:00:00Z",
            },
        ]
    }
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_missing_absolute_url_skips_job():
    """Item sem 'absolute_url' é ignorado."""
    response = {
        "jobs": [
            {
                "id": 1,
                "title": "Eng",
                "location": {"name": "Remote"},
                "updated_at": "2026-05-20T12:00:00Z",
            },
        ]
    }
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_invalid_top_level_schema_returns_empty():
    """API retorna lista em vez de dict com 'jobs' → retorna [] sem crash."""
    mock_client = _make_mock_client([{"title": "Eng"}])  # lista em vez de dict
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_jobs_key_missing_returns_empty():
    """API retorna dict mas sem chave 'jobs' → retorna [] sem crash."""
    mock_client = _make_mock_client({"data": []})  # sem 'jobs'
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


# ── Lever: validação de schema ────────────────────────────────────────────────


async def test_lever_non_list_response_returns_empty():
    """API retorna dict (ex: erro) em vez de lista → retorna [] sem crash."""
    mock_client = _make_mock_client({"error": "rate limited"})
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


# ── Ashby: validação de schema ────────────────────────────────────────────────


async def test_ashby_missing_title_skips_job():
    """Item sem 'title' é ignorado."""
    response = {
        "data": {
            "jobPostings": [
                {
                    "id": "1",
                    "locationName": "Remote",
                    "isRemote": True,
                    "jobPostingAbsoluteUrl": "https://jobs.ashbyhq.com/co/1",
                }
            ]
        }
    }
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_missing_url_skips_job():
    """Item sem 'jobPostingAbsoluteUrl' é ignorado."""
    response = {
        "data": {
            "jobPostings": [{"id": "1", "title": "Eng", "locationName": "Remote", "isRemote": True}]
        }
    }
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_null_job_postings_returns_empty():
    """data.jobPostings é null → retorna [] sem crash."""
    response = {"data": {"jobPostings": None}}
    mock_client = _make_mock_client(response)
    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


# --- logging tests ---


@pytest.mark.asyncio
async def test_greenhouse_logs_scan_start_and_fetched(caplog):
    scanner = GreenhouseScanner()
    payload = {
        "jobs": [
            {
                "title": "SWE",
                "absolute_url": "https://boards.greenhouse.io/co/jobs/1",
                "location": {"name": "Remote"},
                "updated_at": None,
                "content": "",
            }
        ]
    }
    mock_client = _make_mock_client(payload)
    with (
        patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client),
        caplog.at_level(logging.INFO, logger="candidatador.scanner.http_sources"),
    ):
        await scanner.scan(["co"])
    assert "greenhouse" in caplog.text
    assert "scanning" in caplog.text
    assert "fetched" in caplog.text


@pytest.mark.asyncio
async def test_lever_logs_scan_fetched(caplog):
    scanner = LeverScanner()
    payload = [
        {
            "text": "Eng",
            "hostedUrl": "https://jobs.lever.co/co/1",
            "categories": {"location": "Remote"},
            "createdAt": 0,
        }
    ]
    mock_client = _make_mock_client(payload)
    with (
        patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client),
        caplog.at_level(logging.INFO, logger="candidatador.scanner.http_sources"),
    ):
        await scanner.scan(["co"])
    assert "lever" in caplog.text
    assert "fetched" in caplog.text
