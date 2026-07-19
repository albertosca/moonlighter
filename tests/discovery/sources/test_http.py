import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from gauntler.discovery.sources.http import (
    AshbyScanner,
    GreenhouseScanner,
    LeverScanner,
    RecruiteeScanner,
    SmartRecruitersScanner,
    WorkableScanner,
)

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
    assert "Elixir" in jobs[0].description  # QUALITY-01: description extracted


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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs[0].location is None
    assert jobs[0].remote_type is None


async def test_greenhouse_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_empty_jobs_list():
    mock_client = _make_mock_client({"jobs": []})
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs[0].posted_at is None


async def test_lever_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_500_response_skips_company():
    mock_client = _make_mock_client([], status_code=500)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_empty_array_response():
    mock_client = _make_mock_client([])
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["openai"])
    assert len(jobs) == 1
    assert jobs[0].company == "openai"
    assert jobs[0].title == "ML Engineer"
    assert jobs[0].source == "ashby"
    assert "language models" in jobs[0].description  # QUALITY-01: description extracted


async def test_ashby_is_remote_flag_true():
    mock_client = _make_mock_client(ASHBY_RESPONSE)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs[0].remote_type == "onsite"


async def test_ashby_500_response_skips_company():
    mock_client = _make_mock_client({}, status_code=500)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_graphql_error_returns_empty():
    """API returns {"errors": [...]} → no data key → returns []."""
    response = {"errors": [{"message": "Unauthorized"}]}
    mock_client = _make_mock_client(response)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs[0].posted_at is not None
    assert isinstance(jobs[0].posted_at, datetime)


async def test_ashby_empty_job_postings_returns_empty():
    """jobPostings: [] → scan returns []."""
    response = {"data": {"jobPostings": []}}
    mock_client = _make_mock_client(response)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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

    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["stripe", "linear"])
    assert len(jobs) == 2
    assert jobs[0].company == "stripe"
    assert jobs[1].company == "linear"


# ── Greenhouse: schema validation ────────────────────────────────────────────


async def test_greenhouse_missing_title_skips_job():
    """Item with no 'title' is skipped — does not raise KeyError."""
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_missing_absolute_url_skips_job():
    """Item with no 'absolute_url' is skipped."""
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_invalid_top_level_schema_returns_empty():
    """API retorna lista em vez de dict com 'jobs' → retorna [] sem crash."""
    mock_client = _make_mock_client([{"title": "Eng"}])  # lista em vez de dict
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_jobs_key_missing_returns_empty():
    """API retorna dict mas sem chave 'jobs' → retorna [] sem crash."""
    mock_client = _make_mock_client({"data": []})  # sem 'jobs'
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


# ── Lever: schema validation ─────────────────────────────────────────────────


async def test_lever_non_list_response_returns_empty():
    """API retorna dict (ex: erro) em vez de lista → retorna [] sem crash."""
    mock_client = _make_mock_client({"error": "rate limited"})
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


# ── Ashby: schema validation ─────────────────────────────────────────────────


async def test_ashby_missing_title_skips_job():
    """Item with no 'title' is skipped."""
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
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_missing_url_skips_job():
    """Item with no 'jobPostingAbsoluteUrl' is skipped."""
    response = {
        "data": {
            "jobPostings": [{"id": "1", "title": "Eng", "locationName": "Remote", "isRemote": True}]
        }
    }
    mock_client = _make_mock_client(response)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_null_job_postings_returns_empty():
    """data.jobPostings is null → returns [] without crashing."""
    response = {"data": {"jobPostings": None}}
    mock_client = _make_mock_client(response)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        caplog.at_level(logging.INFO, logger="gauntler.discovery.sources.http"),
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
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        caplog.at_level(logging.INFO, logger="gauntler.discovery.sources.http"),
    ):
        await scanner.scan(["co"])
    assert "lever" in caplog.text
    assert "fetched" in caplog.text


async def test_ashby_jobpostings_not_a_list_returns_empty():
    """jobPostings with an unexpected shape (not a list, but truthy) → [] (http_sources.py:171)."""
    response = {"data": {"jobPostings": {"unexpected": "shape"}}}
    mock_client = _make_mock_client(response)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


@pytest.mark.parametrize(
    "Scanner",
    [GreenhouseScanner, LeverScanner, AshbyScanner, WorkableScanner, RecruiteeScanner],
)
async def test_scan_skips_fetch_exceptions(Scanner):
    """_fetch raises → gather(return_exceptions) returns the exception → ignored (not a list)."""
    mock_client = _make_mock_client({})
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch.object(Scanner, "_fetch", new=AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        jobs = await Scanner().scan(["co"])
    assert jobs == []


# --- WorkableScanner tests ---

WORKABLE_RESPONSE = {
    "name": "Acme",
    "jobs": [
        {
            "title": "Staff Engineer",
            "shortcode": "ABC123",
            "application_url": "https://apply.workable.com/j/ABC123/apply",
            "city": "Lisbon",
            "state": "",
            "country": "Portugal",
            "telecommuting": True,
            "description": "<p>Build <b>things</b></p>",
        }
    ],
}


async def test_workable_maps_fields_and_strips_html():
    mock_client = _make_mock_client(WORKABLE_RESPONSE)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source == "workable"
    assert j.company == "acme"
    assert j.title == "Staff Engineer"
    assert j.url == "https://apply.workable.com/j/ABC123/apply"
    assert j.location == "Lisbon, Portugal"
    assert j.remote_type == "remote"  # telecommuting True wins over location
    assert j.description == "Build  things"


async def test_workable_skips_entry_without_title():
    response = {
        "jobs": [
            {
                "title": "",
                "shortcode": "X",
                "application_url": "https://apply.workable.com/j/X/apply",
            }
        ]
    }
    mock_client = _make_mock_client(response)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_skips_entry_without_url():
    response = {"jobs": [{"title": "Eng", "shortcode": "X", "application_url": ""}]}
    mock_client = _make_mock_client(response)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_no_telecommuting_uses_location():
    response = {
        "jobs": [
            {
                "title": "Eng",
                "shortcode": "X",
                "application_url": "https://apply.workable.com/j/X/apply",
                "city": "Berlin",
                "country": "Germany",
                "telecommuting": False,
            }
        ]
    }
    mock_client = _make_mock_client(response)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs[0].remote_type == "onsite"


async def test_workable_missing_location_parts():
    response = {
        "jobs": [
            {
                "title": "Eng",
                "shortcode": "X",
                "application_url": "https://apply.workable.com/j/X/apply",
            }
        ]
    }
    mock_client = _make_mock_client(response)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs[0].location is None
    assert jobs[0].remote_type is None


async def test_workable_500_response_skips_company():
    mock_client = _make_mock_client({}, status_code=500)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_non_dict_response_returns_empty():
    mock_client = _make_mock_client([{"title": "Eng"}])
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_missing_jobs_key_returns_empty():
    mock_client = _make_mock_client({"name": "Acme"})
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


# --- RecruiteeScanner tests ---

RECRUITEE_RESPONSE = {
    "offers": [
        {
            "title": "Backend Dev",
            "id": 42,
            "slug": "backend-dev",
            "careers_apply_url": "https://x.recruitee.com/o/backend-dev/c/new",
            "location": "Amsterdam, Netherlands",
            "remote": False,
            "description": "<ul><li>Go</li></ul>",
        }
    ]
}


async def test_recruitee_maps_fields_and_strips_html():
    mock_client = _make_mock_client(RECRUITEE_RESPONSE)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source == "recruitee"
    assert j.company == "acme"
    assert j.title == "Backend Dev"
    assert j.url == "https://x.recruitee.com/o/backend-dev/c/new"
    assert j.location == "Amsterdam, Netherlands"
    assert j.remote_type == "onsite"  # remote False, falls back to location text
    assert j.description == "Go"


async def test_recruitee_remote_flag_true():
    response = {
        "offers": [
            {
                "title": "Eng",
                "careers_apply_url": "https://x.recruitee.com/o/eng/c/new",
                "location": "Anywhere",
                "remote": True,
            }
        ]
    }
    mock_client = _make_mock_client(response)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs[0].remote_type == "remote"


async def test_recruitee_skips_entry_without_title():
    response = {"offers": [{"title": "", "careers_apply_url": ""}]}
    mock_client = _make_mock_client(response)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_skips_entry_without_url():
    response = {"offers": [{"title": "Eng", "careers_apply_url": ""}]}
    mock_client = _make_mock_client(response)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_500_response_skips_company():
    mock_client = _make_mock_client({}, status_code=500)
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_non_dict_response_returns_empty():
    mock_client = _make_mock_client([{"title": "Eng"}])
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_missing_offers_key_returns_empty():
    mock_client = _make_mock_client({"other": []})
    with patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


# --- SmartRecruitersScanner tests ---

_SR_LIST_P1 = {
    "offset": 0,
    "limit": 1,
    "totalFound": 2,
    "content": [
        {
            "id": "744000000000001",
            "uuid": "u1",
            "name": "SRE",
            "location": {"city": "Remote", "country": "US", "remote": True, "hybrid": False},
        }
    ],
}
_SR_LIST_P2 = {
    "offset": 1,
    "limit": 1,
    "totalFound": 2,
    "content": [
        {
            "id": "744000000000002",
            "uuid": "u2",
            "name": "Data Eng",
            "location": {"city": "NYC", "country": "US", "remote": False, "hybrid": True},
        }
    ],
}
_SR_DETAIL = {"jobAd": {"sections": {"jobDescription": {"text": "<p>Own the pipeline</p>"}}}}


def _sr_response(payload, status_code=200):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = payload
    return mock_response


def _make_url_branching_client(url_map):
    """A mock client whose .get(url) branches on a substring match in url_map.

    url_map: dict[str substring -> response payload]. Raises AssertionError on a URL
    that matches no substring, so a test with an unexpected call fails loudly instead
    of silently succeeding.
    """

    async def fake_get(url, headers=None):
        for substring, payload in url_map.items():
            if substring in url:
                return _sr_response(payload)
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_smartrecruiters_paginates_and_fetches_detail():
    mock_client = _make_url_branching_client(
        {
            "postings?limit=100&offset=0": _SR_LIST_P1,
            "postings?limit=100&offset=1": _SR_LIST_P2,
            "postings/744000000000001": _SR_DETAIL,
            "postings/744000000000002": _SR_DETAIL,
        }
    )
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["Visa"])

    assert len(jobs) == 2
    first, second = jobs
    assert first.source == "smartrecruiters"
    assert first.company == "Visa"
    assert first.title == "SRE"
    assert first.url == "https://jobs.smartrecruiters.com/Visa/744000000000001"
    assert first.remote_type == "remote"
    assert first.description == "Own the pipeline"

    assert second.title == "Data Eng"
    assert second.url == "https://jobs.smartrecruiters.com/Visa/744000000000002"
    assert second.remote_type == "hybrid"
    assert second.description == "Own the pipeline"


async def test_smartrecruiters_empty_feed_makes_no_detail_call():
    empty_page = {"offset": 0, "limit": 100, "totalFound": 0, "content": []}
    mock_client = _make_url_branching_client({"postings?limit=100&offset=0": empty_page})
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()) as mock_sleep,
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []
    mock_sleep.assert_not_called()
    # only the single list call was made, no detail call (asserted implicitly by
    # _make_url_branching_client raising on any unmapped URL, e.g. a detail URL)
    assert mock_client.get.await_count == 1


async def test_smartrecruiters_pagination_terminates_when_content_shorter_than_limit():
    # totalFound overstates what's actually returned; the loop must still terminate
    # because `content` comes back empty on the second page, not because offset caught up.
    page = {"offset": 0, "limit": 100, "totalFound": 5, "content": []}
    mock_client = _make_url_branching_client({"postings?limit=100&offset=0": page})
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []
    assert mock_client.get.await_count == 1


async def test_smartrecruiters_pagination_terminates_when_offset_reaches_total():
    mock_client = _make_url_branching_client(
        {
            "postings?limit=100&offset=0": _SR_LIST_P1,
            "postings?limit=100&offset=1": _SR_LIST_P2,
            "postings/744000000000001": _SR_DETAIL,
            "postings/744000000000002": _SR_DETAIL,
        }
    )
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        await SmartRecruitersScanner().scan(["Visa"])
    # exactly 2 list calls (offset=0, offset=1) then it stops -- proves offset>=total
    # terminates the loop rather than spinning past totalFound.
    list_calls = [c for c in mock_client.get.await_args_list if "postings?limit=100" in c.args[0]]
    assert len(list_calls) == 2


def _make_flat_client(response=None, status_code=200, raise_exc=None):
    """Like _make_mock_client but scoped locally to keep SmartRecruiters tests grouped."""
    mock_client = MagicMock()
    if raise_exc:
        mock_client.get = AsyncMock(side_effect=raise_exc)
    else:
        mock_client.get = AsyncMock(return_value=_sr_response(response, status_code=status_code))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_smartrecruiters_500_response_returns_empty():
    mock_client = _make_flat_client({}, status_code=500)
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []


async def test_smartrecruiters_non_dict_list_response_returns_empty():
    mock_client = _make_flat_client([{"content": []}])
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []


async def test_smartrecruiters_network_exception_on_list_skips_company():
    mock_client = _make_flat_client(raise_exc=httpx.ConnectError("timeout"))
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []


async def test_smartrecruiters_detail_500_yields_none_description():
    mock_client = _make_url_branching_client({"postings?limit=100&offset=0": _SR_LIST_P1})

    async def fake_get(url, headers=None):
        if "postings?limit=100&offset=0" in url:
            return _sr_response(_SR_LIST_P1)
        if "postings/744000000000001" in url:
            return _sr_response({}, status_code=500)
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client.get = AsyncMock(side_effect=fake_get)
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert len(jobs) == 1
    assert jobs[0].description is None


async def test_smartrecruiters_detail_network_exception_yields_none_description():
    async def fake_get(url, headers=None):
        if "postings?limit=100&offset=0" in url:
            return _sr_response(_SR_LIST_P1)
        if "postings/744000000000001" in url:
            raise httpx.ConnectError("timeout")
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert len(jobs) == 1
    assert jobs[0].description is None


async def test_smartrecruiters_detail_non_dict_response_yields_none_description():
    async def fake_get(url, headers=None):
        if "postings?limit=100&offset=0" in url:
            return _sr_response(_SR_LIST_P1)
        if "postings/744000000000001" in url:
            return _sr_response([{"jobAd": {}}])
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert len(jobs) == 1
    assert jobs[0].description is None


async def test_smartrecruiters_skips_posting_without_id_or_name():
    page = {
        "offset": 0,
        "limit": 100,
        "totalFound": 2,
        "content": [
            {"id": "", "name": "No ID", "location": {}},
            {"id": "744000000000009", "name": "", "location": {}},
        ],
    }
    mock_client = _make_url_branching_client({"postings?limit=100&offset=0": page})
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []


async def test_smartrecruiters_no_remote_or_hybrid_flags_uses_location_text():
    page = {
        "offset": 0,
        "limit": 100,
        "totalFound": 1,
        "content": [
            {
                "id": "744000000000010",
                "name": "Support",
                "location": {"city": "Berlin", "country": "Germany"},
            }
        ],
    }
    mock_client = _make_url_branching_client(
        {
            "postings?limit=100&offset=0": page,
            "postings/744000000000010": _SR_DETAIL,
        }
    )
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs[0].location == "Berlin, Germany"
    assert jobs[0].remote_type == "onsite"


async def test_smartrecruiters_missing_location_dict():
    page = {
        "offset": 0,
        "limit": 100,
        "totalFound": 1,
        "content": [{"id": "744000000000011", "name": "No Location"}],
    }
    mock_client = _make_url_branching_client(
        {
            "postings?limit=100&offset=0": page,
            "postings/744000000000011": _SR_DETAIL,
        }
    )
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs[0].location is None
    assert jobs[0].remote_type is None


async def test_smartrecruiters_detail_multiple_sections_concatenated_and_html_stripped():
    detail = {
        "jobAd": {
            "sections": {
                "jobDescription": {"text": "<p>Own the pipeline.</p>"},
                "qualifications": {"text": "<ul><li>5+ years</li></ul>"},
                "notASection": "ignored, not a dict",
            }
        }
    }
    page = {
        "offset": 0,
        "limit": 100,
        "totalFound": 1,
        "content": [{"id": "744000000000012", "name": "Eng", "location": {}}],
    }
    mock_client = _make_url_branching_client(
        {
            "postings?limit=100&offset=0": page,
            "postings/744000000000012": detail,
        }
    )
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    description = jobs[0].description
    assert description is not None
    assert "<" not in description and ">" not in description
    assert "Own the pipeline." in description
    assert "5+ years" in description


async def test_smartrecruiters_detail_no_sections_yields_none_description():
    detail = {"jobAd": {"sections": {}}}
    page = {
        "offset": 0,
        "limit": 100,
        "totalFound": 1,
        "content": [{"id": "744000000000013", "name": "Eng", "location": {}}],
    }
    mock_client = _make_url_branching_client(
        {
            "postings?limit=100&offset=0": page,
            "postings/744000000000013": detail,
        }
    )
    with (
        patch("gauntler.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("gauntler.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs[0].description is None
