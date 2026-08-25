import json
import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from moonlighter.discovery.sources.base import ScanStats, SourceStats
from moonlighter.discovery.sources.http import (
    AshbyScanner,
    FetchError,
    GreenhouseScanner,
    GupyScanner,
    HNWhoIsHiringScanner,
    InHireScanner,
    LeverScanner,
    RecruiteeScanner,
    RemoteOKScanner,
    RemotiveScanner,
    SmartRecruitersScanner,
    WeWorkRemotelyScanner,
    WorkableScanner,
    _get_json,
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs[0].location is None
    assert jobs[0].remote_type is None


async def test_greenhouse_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_empty_jobs_list():
    mock_client = _make_mock_client({"jobs": []})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs[0].posted_at is None


async def test_lever_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_500_response_skips_company():
    mock_client = _make_mock_client([], status_code=500)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


async def test_lever_empty_array_response():
    mock_client = _make_mock_client([])
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


# --- AshbyScanner tests ---


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

    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_invalid_top_level_schema_returns_empty():
    """API retorna lista em vez de dict com 'jobs' → retorna [] sem crash."""
    mock_client = _make_mock_client([{"title": "Eng"}])  # lista em vez de dict
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


async def test_greenhouse_jobs_key_missing_returns_empty():
    """API retorna dict mas sem chave 'jobs' → retorna [] sem crash."""
    mock_client = _make_mock_client({"data": []})  # sem 'jobs'
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GreenhouseScanner().scan(["co"])
    assert jobs == []


# ── Lever: schema validation ─────────────────────────────────────────────────


async def test_lever_non_list_response_returns_empty():
    """API retorna dict (ex: erro) em vez de lista → retorna [] sem crash."""
    mock_client = _make_mock_client({"error": "rate limited"})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await LeverScanner().scan(["co"])
    assert jobs == []


# ── Ashby: schema validation ─────────────────────────────────────────────────


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
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        caplog.at_level(logging.INFO, logger="moonlighter.discovery.sources.http"),
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
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        caplog.at_level(logging.INFO, logger="moonlighter.discovery.sources.http"),
    ):
        await scanner.scan(["co"])
    assert "lever" in caplog.text
    assert "fetched" in caplog.text


@pytest.mark.parametrize(
    "Scanner",
    [GreenhouseScanner, LeverScanner, AshbyScanner, WorkableScanner, RecruiteeScanner],
)
async def test_scan_skips_fetch_exceptions(Scanner):
    """_fetch raises → gather(return_exceptions) returns the exception → ignored (not a list)."""
    mock_client = _make_mock_client({})
    with (
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_skips_entry_without_url():
    response = {"jobs": [{"title": "Eng", "shortcode": "X", "application_url": ""}]}
    mock_client = _make_mock_client(response)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs[0].remote_type is None  # bare city: unknown, never invented onsite


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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs[0].location is None
    assert jobs[0].remote_type is None


async def test_workable_500_response_skips_company():
    mock_client = _make_mock_client({}, status_code=500)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_non_dict_response_returns_empty():
    mock_client = _make_mock_client([{"title": "Eng"}])
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_missing_jobs_key_returns_empty():
    mock_client = _make_mock_client({"name": "Acme"})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source == "recruitee"
    assert j.company == "acme"
    assert j.title == "Backend Dev"
    assert j.url == "https://x.recruitee.com/o/backend-dev/c/new"
    assert j.location == "Amsterdam, Netherlands"
    assert j.remote_type is None  # remote False + bare city: unknown, never invented onsite
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
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs[0].remote_type == "remote"


async def test_recruitee_skips_entry_without_title():
    response = {"offers": [{"title": "", "careers_apply_url": ""}]}
    mock_client = _make_mock_client(response)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_skips_entry_without_url():
    response = {"offers": [{"title": "Eng", "careers_apply_url": ""}]}
    mock_client = _make_mock_client(response)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_500_response_skips_company():
    mock_client = _make_mock_client({}, status_code=500)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_non_dict_response_returns_empty():
    mock_client = _make_mock_client([{"title": "Eng"}])
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_missing_offers_key_returns_empty():
    mock_client = _make_mock_client({"other": []})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RecruiteeScanner().scan(["acme"])
    assert jobs == []


async def test_recruitee_custom_domain_entry():
    """An entry containing a dot is a custom career domain. Live-verified
    2026-08-12: careers.tellent.com and jobs.channable.com serve the same
    /api/offers/ payload as {slug}.recruitee.com."""
    ok = MagicMock(status_code=200)
    ok.json.return_value = RECRUITEE_RESPONSE
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok)
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        jobs = await RecruiteeScanner().scan(["jobs.channable.com"])
    assert len(jobs) > 0
    called_url = mock_client.get.call_args.args[0]
    assert called_url == "https://jobs.channable.com/api/offers/"
    assert jobs[0].company == "jobs.channable.com"


async def test_recruitee_slug_entry_unchanged():
    ok = MagicMock(status_code=200)
    ok.json.return_value = RECRUITEE_RESPONSE
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok)
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        await RecruiteeScanner().scan(["acme"])
    assert mock_client.get.call_args.args[0] == "https://acme.recruitee.com/api/offers/"


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
# _SR_LIST_P1 reports totalFound=2 with only 1 item on this page, so _list keeps
# paginating; the detail-failure tests below only care about page 1, so they close
# pagination with this empty second page rather than hand-waving it away like the
# old blanket try/except did.
_SR_LIST_EMPTY_P2 = {"offset": 1, "limit": 1, "totalFound": 2, "content": []}


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
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
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
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()) as mock_sleep,
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
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
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
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
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


async def test_smartrecruiters_zero_limit_field_does_not_spin():
    # The server explicitly reports "limit": 0 while still returning content and a
    # totalFound far larger than what's been consumed so far. If the loop advanced
    # offset by data.get("limit", 100) it would add 0 and re-request the SAME offset
    # forever (bounded here only by _make_url_branching_client raising on an
    # unexpected URL, which would surface as a failure rather than a real hang).
    # Advancing by len(content) instead guarantees the offset moves forward every
    # iteration, so the loop terminates as soon as a page comes back empty.
    spinning_page = {
        "offset": 0,
        "limit": 0,
        "totalFound": 999999,
        "content": [{"id": "1", "uuid": "u1", "name": "Spinner"}],
    }
    empty_page = {"offset": 1, "limit": 0, "totalFound": 999999, "content": []}
    mock_client = _make_url_branching_client(
        {
            "postings?limit=100&offset=0": spinning_page,
            "postings?limit=100&offset=1": empty_page,
            "postings/1": _SR_DETAIL,
        }
    )
    with (
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])

    assert len(jobs) == 1
    list_calls = [c for c in mock_client.get.await_args_list if "postings?limit=100" in c.args[0]]
    assert len(list_calls) == 2


async def test_smartrecruiters_500_response_returns_empty():
    mock_client = _make_flat_client({}, status_code=500)
    with (
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []


async def test_smartrecruiters_non_dict_list_response_returns_empty():
    mock_client = _make_flat_client([{"content": []}])
    with (
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []


async def test_smartrecruiters_network_exception_on_list_skips_company():
    mock_client = _make_flat_client(raise_exc=httpx.ConnectError("timeout"))
    with (
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs == []


async def test_smartrecruiters_detail_500_yields_none_description():
    mock_client = _make_url_branching_client({"postings?limit=100&offset=0": _SR_LIST_P1})

    async def fake_get(url, headers=None):
        if "postings?limit=100&offset=0" in url:
            return _sr_response(_SR_LIST_P1)
        if "postings?limit=100&offset=1" in url:
            return _sr_response(_SR_LIST_EMPTY_P2)
        if "postings/744000000000001" in url:
            return _sr_response({}, status_code=500)
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client.get = AsyncMock(side_effect=fake_get)
    with (
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert len(jobs) == 1
    assert jobs[0].description is None


async def test_smartrecruiters_detail_network_exception_yields_none_description():
    async def fake_get(url, headers=None):
        if "postings?limit=100&offset=0" in url:
            return _sr_response(_SR_LIST_P1)
        if "postings?limit=100&offset=1" in url:
            return _sr_response(_SR_LIST_EMPTY_P2)
        if "postings/744000000000001" in url:
            raise httpx.ConnectError("timeout")
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with (
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert len(jobs) == 1
    assert jobs[0].description is None


async def test_smartrecruiters_detail_non_dict_response_yields_none_description():
    async def fake_get(url, headers=None):
        if "postings?limit=100&offset=0" in url:
            return _sr_response(_SR_LIST_P1)
        if "postings?limit=100&offset=1" in url:
            return _sr_response(_SR_LIST_EMPTY_P2)
        if "postings/744000000000001" in url:
            return _sr_response([{"jobAd": {}}])
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with (
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
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
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
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
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs[0].location == "Berlin, Germany"
    assert jobs[0].remote_type is None  # bare city: unknown, never invented onsite


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
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
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
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
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
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client),
        patch("moonlighter.discovery.sources.http.asyncio.sleep", AsyncMock()),
    ):
        jobs = await SmartRecruitersScanner().scan(["acme"])
    assert jobs[0].description is None


# --- GupyScanner tests ---

_GUPY_P1 = {
    "data": [
        {
            "id": 1,
            "name": "Engenheiro de Software",
            "jobUrl": "https://acme.gupy.io/job/tok?jobBoardSource=gupy_portal",
            "careerPageName": "acme",
            "description": "Construir&nbsp;coisas",
            "city": "",
            "state": "",
            "country": "Brasil",
            "isRemoteWork": True,
            "workplaceType": "remote",
        }
    ],
    "pagination": {"total": 1, "limit": 10, "offset": 0},
}


def _make_gupy_client(url_map):
    """Like _make_url_branching_client: branches the mock client's .get(url) on a
    substring match, raising loudly on an unexpected URL."""

    async def fake_get(url, headers=None):
        for substring, payload in url_map.items():
            if substring in url:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = payload
                return mock_response
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_gupy_scan_maps_fields_and_strips_html():
    mock_client = _make_gupy_client({"offset=0": _GUPY_P1})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan(keywords="engenheiro")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "gupy"
    assert job.company == "acme"
    assert job.title == "Engenheiro de Software"
    assert job.url == "https://acme.gupy.io/job/tok?jobBoardSource=gupy_portal"
    assert job.remote_type == "remote"
    assert job.description == "Construir coisas"


async def test_gupy_missing_title_or_url_is_skipped():
    page = {
        "data": [
            {"id": 1, "jobUrl": "https://x.gupy.io/1"},  # missing name
            {"id": 2, "name": "Eng"},  # missing jobUrl
        ],
        "pagination": {"total": 2, "limit": 10, "offset": 0},
    }
    mock_client = _make_gupy_client({"offset=0": page})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs == []


async def test_gupy_no_remote_work_uses_workplace_type():
    page = {
        "data": [
            {
                "id": 1,
                "name": "Eng",
                "jobUrl": "https://acme.gupy.io/1",
                "careerPageName": "acme",
                "isRemoteWork": False,
                "workplaceType": "hybrid",
            }
        ],
        "pagination": {"total": 1, "limit": 10, "offset": 0},
    }
    mock_client = _make_gupy_client({"offset=0": page})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs[0].remote_type == "hybrid"


async def test_gupy_missing_careerpagename_falls_back_to_gupy():
    page = {
        "data": [{"id": 1, "name": "Eng", "jobUrl": "https://acme.gupy.io/1"}],
        "pagination": {"total": 1, "limit": 10, "offset": 0},
    }
    mock_client = _make_gupy_client({"offset=0": page})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs[0].company == "gupy"


async def test_gupy_no_description_yields_none():
    page = {
        "data": [{"id": 1, "name": "Eng", "jobUrl": "https://acme.gupy.io/1"}],
        "pagination": {"total": 1, "limit": 10, "offset": 0},
    }
    mock_client = _make_gupy_client({"offset=0": page})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs[0].description is None


async def test_gupy_paginates_across_pages():
    p1 = {
        "data": [{"id": 1, "name": "Eng One", "jobUrl": "https://acme.gupy.io/1"}],
        "pagination": {"total": 2, "limit": 1, "offset": 0},
    }
    p2 = {
        "data": [{"id": 2, "name": "Eng Two", "jobUrl": "https://acme.gupy.io/2"}],
        "pagination": {"total": 2, "limit": 1, "offset": 1},
    }
    mock_client = _make_gupy_client({"offset=0": p1, "offset=1": p2})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan(keywords="eng")
    assert [j.title for j in jobs] == ["Eng One", "Eng Two"]
    assert mock_client.get.await_count == 2


async def test_gupy_zero_limit_field_does_not_spin():
    # The server reports "limit": 0 while still returning data and a total far
    # larger than what's been consumed. If the loop advanced offset by
    # data["pagination"]["limit"] it would add 0 and re-request the SAME offset
    # forever (bounded here only by the URL-branching mock raising on an
    # unexpected URL). Advancing by len(page) instead guarantees forward
    # progress every iteration.
    spinning_page = {
        "data": [{"id": 1, "name": "Spinner", "jobUrl": "https://acme.gupy.io/1"}],
        "pagination": {"total": 999999, "limit": 0, "offset": 0},
    }
    empty_page = {"data": [], "pagination": {"total": 999999, "limit": 0, "offset": 1}}
    mock_client = _make_gupy_client({"offset=0": spinning_page, "offset=1": empty_page})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan(keywords="eng")
    assert len(jobs) == 1
    assert mock_client.get.await_count == 2


async def test_gupy_empty_page_terminates_immediately():
    page = {"data": [], "pagination": {"total": 0, "limit": 10, "offset": 0}}
    mock_client = _make_gupy_client({"offset=0": page})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs == []
    assert mock_client.get.await_count == 1


async def test_gupy_500_response_returns_empty():
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs == []


async def test_gupy_non_json_body_returns_empty():
    """A 200 response with a non-JSON body (e.g. a Cloudflare/rate-limit
    interstitial page) must degrade to [] like every other failure mode,
    not raise json.JSONDecodeError out of scan() and abort the whole run."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "<html>", 0)
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs == []


async def test_gupy_non_dict_response_returns_empty():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"data": []}]
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs == []


async def test_gupy_network_exception_returns_empty():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs == []


async def test_gupy_default_keyword_when_not_provided():
    page = {"data": [], "pagination": {"total": 0, "limit": 10, "offset": 0}}
    mock_client = _make_gupy_client({"jobName=&limit=100&offset=0": page})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await GupyScanner().scan()
    assert jobs == []


# --- RemoteOKScanner tests ---


def _make_simple_client(payload, status=200):
    """Single-GET JSON mock client — for scanners that don't paginate."""

    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        mock_response.status_code = status
        mock_response.json.return_value = payload
        mock_response.text = json.dumps(payload) if not isinstance(payload, str) else payload
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


_REMOTEOK_RESPONSE = [
    {"legal": "API Terms of Service: link back to Remote OK..."},
    {
        "id": "123",
        "company": "Acme",
        "position": "Senior Backend Engineer",
        "url": "https://remoteok.com/remote-jobs/123",
        "location": "Worldwide",
        "tags": ["python", "backend"],
        "description": "<p>Build <strong>things</strong>.</p>",
    },
    {
        "id": "124",
        "company": "",
        "position": "Frontend Dev",
        "url": "",  # missing url -> skipped
    },
]


async def test_remoteok_scan_maps_fields_and_skips_legal_notice_and_missing_url():
    mock_client = _make_simple_client(_REMOTEOK_RESPONSE)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemoteOKScanner().scan()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "remoteok"
    assert job.company == "Acme"
    assert job.title == "Senior Backend Engineer"
    assert job.url == "https://remoteok.com/remote-jobs/123"
    assert job.location == "Worldwide"
    assert job.remote_type == "remote"
    assert job.description == "Build things."


async def test_remoteok_missing_company_falls_back_to_source_name():
    response = [
        {
            "position": "Eng",
            "url": "https://remoteok.com/remote-jobs/1",
            "company": "",
        }
    ]
    mock_client = _make_simple_client(response)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemoteOKScanner().scan()
    assert jobs[0].company == "RemoteOK"


async def test_remoteok_network_exception_returns_empty():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemoteOKScanner().scan()
    assert jobs == []


async def test_remoteok_non_200_returns_empty():
    mock_client = _make_simple_client({}, status=500)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemoteOKScanner().scan()
    assert jobs == []


async def test_remoteok_non_list_json_returns_empty():
    mock_client = _make_simple_client({"unexpected": "shape"})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemoteOKScanner().scan()
    assert jobs == []


async def test_remoteok_non_json_body_returns_empty():
    """A 200 response with a non-JSON body (e.g. a Cloudflare interstitial --
    RemoteOK is Cloudflare-fronted) must degrade to [] like every other
    failure mode, not raise json.JSONDecodeError out of scan()."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "<html>", 0)
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemoteOKScanner().scan()
    assert jobs == []


# --- RemotiveScanner tests ---

_REMOTIVE_RESPONSE = {
    "jobs": [
        {
            "id": 1,
            "title": "Senior Python Engineer",
            "company_name": "Acme",
            "url": "https://remotive.com/remote-jobs/1",
            "candidate_required_location": "Worldwide",
            "description": "<p>Build <strong>things</strong>.</p>",
        },
        {
            "id": 2,
            "title": "",  # missing title -> skipped
            "company_name": "Beta",
            "url": "https://remotive.com/remote-jobs/2",
        },
    ]
}


async def test_remotive_scan_maps_fields_and_skips_missing_title():
    mock_client = _make_simple_client(_REMOTIVE_RESPONSE)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemotiveScanner().scan()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "remotive"
    assert job.company == "Acme"
    assert job.title == "Senior Python Engineer"
    assert job.url == "https://remotive.com/remote-jobs/1"
    assert job.location == "Worldwide"
    assert job.remote_type == "remote"
    assert job.description == "Build things."


async def test_remotive_missing_company_falls_back_to_source_name():
    response = {"jobs": [{"title": "Eng", "url": "https://remotive.com/1", "company_name": ""}]}
    mock_client = _make_simple_client(response)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemotiveScanner().scan()
    assert jobs[0].company == "Remotive"


async def test_remotive_no_jobs_key_returns_empty():
    mock_client = _make_simple_client({"job-count": 0})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemotiveScanner().scan()
    assert jobs == []


async def test_remotive_network_exception_returns_empty():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemotiveScanner().scan()
    assert jobs == []


async def test_remotive_non_dict_json_returns_empty():
    mock_client = _make_simple_client(["unexpected", "shape"])
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemotiveScanner().scan()
    assert jobs == []


async def test_remotive_non_json_body_returns_empty():
    """A 200 response with a non-JSON body must degrade to [] like every
    other failure mode, not raise json.JSONDecodeError out of scan()."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "<html>", 0)
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemotiveScanner().scan()
    assert jobs == []


async def test_remotive_non_200_returns_empty():
    mock_client = _make_simple_client({}, status=500)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await RemotiveScanner().scan()
    assert jobs == []


# --- WeWorkRemotelyScanner tests ---

_WWR_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>We Work Remotely</title>
    <item>
      <title>Acme: Senior Backend Engineer</title>
      <region>Anywhere in the World</region>
      <description>&lt;p&gt;Build &lt;strong&gt;things&lt;/strong&gt;.&lt;/p&gt;</description>
      <pubDate>Tue, 30 Jun 2026 20:32:52 +0000</pubDate>
      <link>https://weworkremotely.com/remote-jobs/acme-senior-backend-engineer</link>
    </item>
    <item>
      <title>Frontend Developer Wanted</title>
      <region>USA Only</region>
      <description>No colon in title, no company prefix.</description>
      <pubDate>Wed, 01 Jul 2026 10:00:00 +0000</pubDate>
      <link>https://weworkremotely.com/remote-jobs/frontend-developer-wanted</link>
    </item>
    <item>
      <title>Missing Link Co: Some Role</title>
      <region>Worldwide</region>
      <description>No link element -- must be skipped.</description>
      <pubDate>Wed, 01 Jul 2026 10:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""


def _make_rss_client(body, status=200):
    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        mock_response.status_code = status
        mock_response.text = body
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_wwr_scan_splits_company_from_title_and_strips_html():
    mock_client = _make_rss_client(_WWR_RSS)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WeWorkRemotelyScanner().scan()

    assert len(jobs) == 2  # third item has no <link>, skipped
    job = jobs[0]
    assert job.source == "weworkremotely"
    assert job.company == "Acme"
    assert job.title == "Senior Backend Engineer"
    assert job.url == "https://weworkremotely.com/remote-jobs/acme-senior-backend-engineer"
    assert job.location == "Anywhere in the World"
    assert job.remote_type == "remote"
    assert job.description == "Build things."
    assert job.posted_at is not None
    assert job.posted_at.year == 2026 and job.posted_at.month == 6 and job.posted_at.day == 30


async def test_wwr_title_without_colon_falls_back_to_source_name_company():
    mock_client = _make_rss_client(_WWR_RSS)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WeWorkRemotelyScanner().scan()
    no_colon_job = next(j for j in jobs if j.title == "Frontend Developer Wanted")
    assert no_colon_job.company == "WeWorkRemotely"


async def test_wwr_network_exception_returns_empty():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WeWorkRemotelyScanner().scan()
    assert jobs == []


async def test_wwr_non_200_returns_empty():
    mock_client = _make_rss_client("", status=500)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WeWorkRemotelyScanner().scan()
    assert jobs == []


async def test_wwr_malformed_xml_returns_empty():
    mock_client = _make_rss_client("<not-valid-xml")
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WeWorkRemotelyScanner().scan()
    assert jobs == []


async def test_wwr_missing_pubdate_leaves_posted_at_none():
    rss = _WWR_RSS.replace("<pubDate>Tue, 30 Jun 2026 20:32:52 +0000</pubDate>", "", 1)
    mock_client = _make_rss_client(rss)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WeWorkRemotelyScanner().scan()
    assert jobs[0].posted_at is None


async def test_wwr_missing_description_yields_none():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Acme: No Description Role</title>
      <region>Worldwide</region>
      <link>https://weworkremotely.com/remote-jobs/acme-no-description-role</link>
    </item>
  </channel>
</rss>"""
    mock_client = _make_rss_client(rss)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await WeWorkRemotelyScanner().scan()
    assert jobs[0].description is None


# --- HNWhoIsHiringScanner tests ---


def _make_hn_client(url_map):
    """Branches on exact URL match (HN's API is one-resource-per-URL, no
    query params to substring-match on)."""

    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        if url in url_map:
            mock_response.status_code = 200
            mock_response.json.return_value = url_map[url]
        else:
            mock_response.status_code = 404
            mock_response.json.return_value = None
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


_HN_BASE = "https://hacker-news.firebaseio.com/v0"


def _hn_url_map(*, thread_id=100, kids=(201, 202, 203)):
    return {
        f"{_HN_BASE}/user/whoishiring.json": {"submitted": [99, thread_id]},
        f"{_HN_BASE}/item/99.json": {"id": 99, "title": "Ask HN: Freelancer? Seeking freelancer?"},
        f"{_HN_BASE}/item/{thread_id}.json": {
            "id": thread_id,
            "title": "Ask HN: Who is hiring? (July 2026)",
            "kids": list(kids),
        },
        f"{_HN_BASE}/item/201.json": {
            "id": 201,
            "text": "Acme | Remote | Full-time&lt;p&gt;Build things.&lt;/p&gt;",
        },
        f"{_HN_BASE}/item/202.json": {
            "id": 202,
            "text": "No separator in this first line at all just prose",
        },
        f"{_HN_BASE}/item/203.json": {"id": 203, "deleted": True, "text": "gone"},
    }


async def test_hn_scan_finds_thread_and_parses_pipe_separated_title():
    mock_client = _make_hn_client(_hn_url_map())
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()

    acme = next(j for j in jobs if j.company == "Acme")
    assert acme.source == "hn_whoishiring"
    assert acme.title == "Remote | Full-time Build things."
    assert acme.url == "https://news.ycombinator.com/item?id=201"
    assert acme.remote_type is None


async def test_hn_parse_title_truncates_long_rest_after_separator():
    """Live-discovered (2026-07-21): HN comments render paragraphs as <p>,
    which the tag-strip turns into a space, not a newline -- so 'first line'
    is really 'the whole flattened comment' and an unbounded `rest` after
    the first separator became the entire ~1200-char posting. Cap it like
    the no-separator fallback already caps full_text."""
    long_rest = "Senior Engineer, Genomics Infrastructure | Memphis, TN | ONSITE or REMOTE | " + (
        "x" * 200
    )
    text = f"Acme | {long_rest}"
    url_map = _hn_url_map(kids=(201,))
    url_map[f"{_HN_BASE}/item/201.json"] = {"id": 201, "text": text}
    mock_client = _make_hn_client(url_map)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    job = next(j for j in jobs if j.company == "Acme")
    assert len(job.title) <= 81  # 80 chars + the "…" ellipsis
    assert job.title.endswith("…")


async def test_hn_scan_falls_back_to_prose_when_no_separator():
    mock_client = _make_hn_client(_hn_url_map())
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()

    fallback = next(j for j in jobs if j.url.endswith("id=202"))
    assert fallback.company == "HN Who's Hiring"
    assert "No separator in this first line" in fallback.title


async def test_hn_scan_skips_deleted_comments():
    mock_client = _make_hn_client(_hn_url_map())
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert all(not j.url.endswith("id=203") for j in jobs)


async def test_hn_no_who_is_hiring_thread_found_returns_empty():
    url_map = {
        f"{_HN_BASE}/user/whoishiring.json": {"submitted": [99]},
        f"{_HN_BASE}/item/99.json": {"id": 99, "title": "Ask HN: Freelancer? Seeking freelancer?"},
    }
    mock_client = _make_hn_client(url_map)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_thread_with_no_kids_returns_empty():
    url_map = {
        f"{_HN_BASE}/user/whoishiring.json": {"submitted": [100]},
        f"{_HN_BASE}/item/100.json": {"id": 100, "title": "Ask HN: Who is hiring? (July 2026)"},
    }
    mock_client = _make_hn_client(url_map)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_network_exception_on_user_lookup_returns_empty():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_user_lookup_non_200_returns_empty():
    mock_client = _make_hn_client({})  # every URL 404s
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_thread_lookup_skips_item_non_200_and_continues():
    url_map = {
        f"{_HN_BASE}/user/whoishiring.json": {"submitted": [98, 100]},
        # 98 is the first candidate but its own item fetch 404s -- loop must
        # continue to 100 rather than stopping.
        f"{_HN_BASE}/item/100.json": {
            "id": 100,
            "title": "Ask HN: Who is hiring? (July 2026)",
            "kids": [201],
        },
        f"{_HN_BASE}/item/201.json": {"id": 201, "text": "Acme | Remote"},
    }
    mock_client = _make_hn_client(url_map)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert len(jobs) == 1
    assert jobs[0].company == "Acme"


async def test_hn_thread_lookup_skips_item_exception_and_continues():
    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        if url == f"{_HN_BASE}/user/whoishiring.json":
            mock_response.status_code = 200
            mock_response.json.return_value = {"submitted": [98, 100]}
            return mock_response
        if url == f"{_HN_BASE}/item/98.json":
            raise httpx.ConnectError("boom")
        if url == f"{_HN_BASE}/item/100.json":
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": 100,
                "title": "Ask HN: Who is hiring? (July 2026)",
                "kids": [],
            }
            return mock_response
        mock_response.status_code = 404
        mock_response.json.return_value = None
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []  # thread found (id 100), but it has no kids


async def test_hn_fetch_kids_non_200_returns_empty():
    """The first call to /item/100.json (inside _find_latest_thread, checking
    the title) must succeed; the SECOND call to that same URL (inside
    _fetch_kids) is what returns non-200."""

    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        if url == f"{_HN_BASE}/user/whoishiring.json":
            mock_response.status_code = 200
            mock_response.json.return_value = {"submitted": [100]}
            return mock_response
        if url == f"{_HN_BASE}/item/100.json":
            if not getattr(fake_get, "_seen", False):
                fake_get._seen = True
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "id": 100,
                    "title": "Ask HN: Who is hiring? (July 2026)",
                }
                return mock_response
            mock_response.status_code = 500
            mock_response.json.return_value = None
            return mock_response
        mock_response.status_code = 404
        mock_response.json.return_value = None
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_fetch_kids_exception_returns_empty():
    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        if url == f"{_HN_BASE}/user/whoishiring.json":
            mock_response.status_code = 200
            mock_response.json.return_value = {"submitted": [100]}
            return mock_response
        if url == f"{_HN_BASE}/item/100.json":
            # First call (thread-title lookup, inside _find_latest_thread)
            # must succeed; the SECOND call to the same URL (_fetch_kids)
            # is what raises.
            if not getattr(fake_get, "_seen", False):
                fake_get._seen = True
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "id": 100,
                    "title": "Ask HN: Who is hiring? (July 2026)",
                }
                return mock_response
            raise httpx.ConnectError("boom")
        mock_response.status_code = 404
        mock_response.json.return_value = None
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_fetch_comment_non_200_is_dropped():
    url_map = _hn_url_map(kids=(201,))
    del url_map[f"{_HN_BASE}/item/201.json"]  # 201 now 404s -> comment dropped
    mock_client = _make_hn_client(url_map)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_fetch_comment_exception_is_dropped():
    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        if url == f"{_HN_BASE}/item/201.json":
            raise httpx.ConnectError("boom")
        base_map = _hn_url_map(kids=(201,))
        if url in base_map:
            mock_response.status_code = 200
            mock_response.json.return_value = base_map[url]
            return mock_response
        mock_response.status_code = 404
        mock_response.json.return_value = None
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_comment_with_empty_text_is_dropped():
    url_map = _hn_url_map(kids=(201,))
    url_map[f"{_HN_BASE}/item/201.json"] = {"id": 201, "text": ""}
    mock_client = _make_hn_client(url_map)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_comment_with_only_tags_strips_to_empty_and_is_dropped():
    url_map = _hn_url_map(kids=(201,))
    url_map[f"{_HN_BASE}/item/201.json"] = {"id": 201, "text": "<p></p>"}
    mock_client = _make_hn_client(url_map)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert jobs == []


async def test_hn_parse_title_falls_through_when_separator_leads_with_empty_company():
    """A first line starting with the '|' separator strips to an empty
    company on that attempt -- must fall through (not return an empty
    company) to try '-' next and, since this fixture has no '-' either,
    all the way to the final prose fallback."""
    text = "| Remote position available now for engineers"
    url_map = _hn_url_map(kids=(201,))
    url_map[f"{_HN_BASE}/item/201.json"] = {"id": 201, "text": text}
    mock_client = _make_hn_client(url_map)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan()
    assert len(jobs) == 1
    assert jobs[0].company == "HN Who's Hiring"
    assert jobs[0].title == text


# --- AshbyScanner ---
# The GraphQL board API these tests used to target was retired: it answers HTTP 200
# with {"errors":[{"message":'Cannot query field "jobPostings" on type "Query"'}]},
# which the scanner turned into [] — so every Ashby company reported zero openings
# and nothing was logged. Field shapes below are copied from a live response of the
# current endpoint (api.ashbyhq.com/posting-api/job-board/<slug>), 2026-08-03.


def _ashby_response(*jobs):
    return {"jobs": list(jobs), "apiVersion": "v1"}


ASHBY_JOB = {
    "id": "d3bc1ced",
    "title": "ML Engineer",
    "location": "Remote",
    "isRemote": True,
    "isListed": True,
    "publishedAt": "2026-05-01T20:13:45.158+00:00",
    "descriptionPlain": "Train and serve large language models.",
    "jobUrl": "https://jobs.ashbyhq.com/openai/d3bc1ced",
}


async def test_ashby_scan_success():
    mock_client = _make_mock_client(_ashby_response(ASHBY_JOB))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["openai"])
    assert len(jobs) == 1
    assert jobs[0].company == "openai"
    assert jobs[0].title == "ML Engineer"
    assert jobs[0].source == "ashby"
    assert jobs[0].url == "https://jobs.ashbyhq.com/openai/d3bc1ced"
    assert "language models" in jobs[0].description


async def test_ashby_uses_the_rest_board_endpoint():
    """Guards the regression directly: a POST to the retired GraphQL endpoint is
    what made every company look empty."""
    mock_client = _make_mock_client(_ashby_response(ASHBY_JOB))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        await AshbyScanner().scan(["openai"])
    mock_client.post.assert_not_called()
    url = mock_client.get.call_args.args[0]
    assert url == "https://api.ashbyhq.com/posting-api/job-board/openai"


async def test_ashby_is_remote_flag_true():
    mock_client = _make_mock_client(_ashby_response(ASHBY_JOB))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["openai"])
    assert jobs[0].remote_type == "remote"


async def test_ashby_is_remote_flag_false_uses_location():
    job = {**ASHBY_JOB, "location": "São Paulo, Brazil", "isRemote": False}
    mock_client = _make_mock_client(_ashby_response(job))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs[0].remote_type is None  # bare city: unknown, never invented onsite


async def test_ashby_unlisted_job_is_skipped():
    """isListed=False means the posting is not public — surfacing it would send the
    candidate to a page that is not accepting applications."""
    job = {**ASHBY_JOB, "isListed": False}
    mock_client = _make_mock_client(_ashby_response(job))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_500_response_skips_company():
    mock_client = _make_mock_client({}, status_code=500)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_network_exception_skips_company():
    mock_client = _make_mock_client(raise_exc=httpx.ConnectError("timeout"))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_missing_published_at_returns_none():
    job = {k: v for k, v in ASHBY_JOB.items() if k != "publishedAt"}
    mock_client = _make_mock_client(_ashby_response(job))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert len(jobs) == 1
    assert jobs[0].posted_at is None


async def test_ashby_published_at_parsed_as_datetime():
    """The live API returns a timezone-aware ISO timestamp, not a bare date."""
    mock_client = _make_mock_client(_ashby_response(ASHBY_JOB))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["openai"])
    assert isinstance(jobs[0].posted_at, datetime)


async def test_ashby_unparseable_published_at_returns_none():
    job = {**ASHBY_JOB, "publishedAt": "not-a-date"}
    mock_client = _make_mock_client(_ashby_response(job))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs[0].posted_at is None


async def test_ashby_empty_jobs_returns_empty():
    mock_client = _make_mock_client(_ashby_response())
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_missing_title_skips_job():
    job = {k: v for k, v in ASHBY_JOB.items() if k != "title"}
    mock_client = _make_mock_client(_ashby_response(job))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_missing_url_skips_job():
    job = {k: v for k, v in ASHBY_JOB.items() if k != "jobUrl"}
    mock_client = _make_mock_client(_ashby_response(job))
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_jobs_not_a_list_returns_empty():
    mock_client = _make_mock_client({"jobs": {"unexpected": "shape"}})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_null_jobs_returns_empty():
    mock_client = _make_mock_client({"jobs": None})
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


async def test_ashby_non_dict_response_returns_empty():
    mock_client = _make_mock_client([{"title": "Eng"}])
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs == []


# --- _get_json + per-source stats counting ---


def _mock_client_cls(mock_client):
    cls = MagicMock()
    cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return cls


@pytest.mark.asyncio
async def test_get_json_raises_on_network_error():
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(FetchError):
        await _get_json(client, "https://example.test/x")


@pytest.mark.asyncio
async def test_get_json_raises_on_non_200():
    client = AsyncMock()
    response = MagicMock(status_code=500)
    client.get = AsyncMock(return_value=response)
    with pytest.raises(FetchError, match="HTTP 500"):
        await _get_json(client, "https://example.test/x")


@pytest.mark.asyncio
async def test_get_json_raises_on_non_json_body():
    client = AsyncMock()
    response = MagicMock(status_code=200)
    response.json.side_effect = ValueError("not json")
    client.get = AsyncMock(return_value=response)
    with pytest.raises(FetchError, match="non-JSON"):
        await _get_json(client, "https://example.test/x")


@pytest.mark.asyncio
async def test_gather_jobs_counts_failures_per_source():
    """One slug succeeds, one errors: the error is COUNTED in stats, not silently
    dropped — [] from a broken API must stay distinguishable from no openings."""
    ok = MagicMock(status_code=200)
    ok.json.return_value = GREENHOUSE_RESPONSE
    boom = MagicMock(status_code=500)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[ok, boom])
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        stats: ScanStats = {}
        jobs = await GreenhouseScanner().scan(["stripe", "deadco"], stats=stats)
    assert len(jobs) == 1
    assert stats["greenhouse"] == SourceStats(companies=2, jobs=1, errors=1)


@pytest.mark.asyncio
async def test_scan_without_stats_still_works():
    ok = MagicMock(status_code=200)
    ok.json.return_value = GREENHOUSE_RESPONSE
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok)
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        jobs = await GreenhouseScanner().scan(["stripe"])
    assert len(jobs) == 1


# --- portal scanners: stats via the same helper ---


@pytest.mark.asyncio
async def test_remoteok_records_stats_on_failure():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(status_code=503))
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        stats: ScanStats = {}
        jobs = await RemoteOKScanner().scan(stats=stats)
    assert jobs == []
    assert stats["remoteok"] == SourceStats(companies=0, jobs=0, errors=1)


@pytest.mark.asyncio
async def test_remoteok_records_stats_on_success():
    ok = MagicMock(status_code=200)
    ok.json.return_value = _REMOTEOK_RESPONSE
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok)
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        stats: ScanStats = {}
        jobs = await RemoteOKScanner().scan(stats=stats)
    assert stats["remoteok"].jobs == len(jobs) > 0
    assert stats["remoteok"].errors == 0


@pytest.mark.asyncio
async def test_remotive_records_stats_on_failure():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(status_code=503))
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        stats: ScanStats = {}
        jobs = await RemotiveScanner().scan(stats=stats)
    assert jobs == []
    assert stats["remotive"] == SourceStats(companies=0, jobs=0, errors=1)


@pytest.mark.asyncio
async def test_remotive_records_stats_on_success():
    ok = MagicMock(status_code=200)
    ok.json.return_value = _REMOTIVE_RESPONSE
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok)
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        stats: ScanStats = {}
        jobs = await RemotiveScanner().scan(stats=stats)
    assert stats["remotive"].jobs == len(jobs) > 0
    assert stats["remotive"].errors == 0


@pytest.mark.asyncio
async def test_wwr_records_stats_on_failure():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(status_code=503))
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        stats: ScanStats = {}
        jobs = await WeWorkRemotelyScanner().scan(stats=stats)
    assert jobs == []
    assert stats["weworkremotely"] == SourceStats(companies=0, jobs=0, errors=1)


@pytest.mark.asyncio
async def test_wwr_records_stats_on_success():
    ok = MagicMock(status_code=200)
    ok.text = _WWR_RSS
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok)
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        stats: ScanStats = {}
        jobs = await WeWorkRemotelyScanner().scan(stats=stats)
    assert stats["weworkremotely"].jobs == len(jobs) > 0
    assert stats["weworkremotely"].errors == 0


@pytest.mark.asyncio
async def test_gupy_records_stats_on_failure():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(status_code=503))
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        stats: ScanStats = {}
        jobs = await GupyScanner().scan(keywords="eng", stats=stats)
    assert jobs == []
    assert stats["gupy"] == SourceStats(companies=0, jobs=0, errors=1)


@pytest.mark.asyncio
async def test_gupy_records_stats_on_success():
    ok = MagicMock(status_code=200)
    ok.json.return_value = _GUPY_P1
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=ok)
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        stats: ScanStats = {}
        jobs = await GupyScanner().scan(keywords="eng", stats=stats)
    assert stats["gupy"].jobs == len(jobs) > 0
    assert stats["gupy"].errors == 0


@pytest.mark.asyncio
async def test_hn_records_stats_on_failure_when_no_thread_found():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(status_code=503))
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        stats: ScanStats = {}
        jobs = await HNWhoIsHiringScanner().scan(stats=stats)
    assert jobs == []
    assert stats["hn_whoishiring"] == SourceStats(companies=0, jobs=0, errors=1)


@pytest.mark.asyncio
async def test_hn_records_stats_on_success():
    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        url_map = _hn_url_map()
        if url in url_map:
            mock_response.status_code = 200
            mock_response.json.return_value = url_map[url]
        else:
            mock_response.status_code = 404
            mock_response.json.return_value = None
        return mock_response

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    with patch("httpx.AsyncClient", _mock_client_cls(mock_client)):
        stats: ScanStats = {}
        jobs = await HNWhoIsHiringScanner().scan(stats=stats)
    assert stats["hn_whoishiring"].jobs == len(jobs) > 0
    # kid 203 is a deleted comment (dropped, not an error); kid 202 has no
    # separator and falls back to the prose title (also not an error) -- only
    # a genuine fetch/parse failure should count.
    assert stats["hn_whoishiring"].errors == 0


@pytest.mark.asyncio
async def test_hn_records_stats_counts_comment_gather_exceptions():
    """_fetch_comment already swallows its own network/HTTP failures into None
    (a 404'd or dead comment is indistinguishable and not an error, per the
    brief) -- but asyncio.gather(return_exceptions=True) can still surface a
    genuine Exception object if something above that try/except blows up.
    That's what the error-counting formula is for; force one here directly."""
    url_map = _hn_url_map(kids=(201, 202))
    mock_client = _make_hn_client(url_map)
    with (
        patch("httpx.AsyncClient", _mock_client_cls(mock_client)),
        patch.object(
            HNWhoIsHiringScanner,
            "_fetch_comment",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
    ):
        stats: ScanStats = {}
        jobs = await HNWhoIsHiringScanner().scan(stats=stats)
    assert jobs == []
    assert stats["hn_whoishiring"] == SourceStats(companies=0, jobs=0, errors=2)


async def test_hn_comment_fetch_failures_count_as_errors_deleted_do_not():
    # A 404 on a comment used to flatten into the same None as a deleted
    # comment, so per-comment fetch failures never reached the stats.
    url_map = _hn_url_map(kids=(201, 203, 999))  # 999 is absent -> 404
    mock_client = _make_hn_client(url_map)
    stats = {}
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await HNWhoIsHiringScanner().scan(stats=stats)

    assert [j.company for j in jobs] == ["Acme"]
    s = stats["hn_whoishiring"]
    assert s.jobs == 1
    assert s.errors == 1  # the 404; the deleted comment 203 is not an error


# ── InHire ──────────────────────────────────────────────────────────────────

INHIRE_PAGE = {
    "tenantName": "Alice",
    "jobsPage": [
        {
            "jobId": "832b18f4-adf6-4c32-8e1b-18321e0b8069",
            "displayName": " Design l Creative Design ",
            "status": "published",
            "workplaceType": "Hybrid",
            "location": "São Paulo, SP, BR",
        },
        {
            "jobId": "aaaa",
            "displayName": "Backend Engineer",
            "status": "published",
            "workplaceType": "Remote",
            "location": "BR",
        },
        {
            "jobId": "bbbb",
            "displayName": "Old Role",
            "status": "draft",
            "workplaceType": "On-site",
            "location": "SP",
        },
    ],
}


INHIRE_DETAIL = {
    "832b18f4-adf6-4c32-8e1b-18321e0b8069": {
        "displayName": "Design l Creative Design",
        "description": "<p>Craft <b>visual</b> systems.</p>",
    },
    "aaaa": {
        "displayName": "Backend Engineer",
        "description": "<div>Build APIs<br>in Python.</div>",
    },
}


def _make_inhire_client(page=INHIRE_PAGE, details=INHIRE_DETAIL, detail_status=200):
    """Mock client that serves the listing at BASE and per-job details at
    BASE/{jobId} — the two-endpoint shape the real API has."""
    mock_client = MagicMock()

    async def get(url, headers=None):
        resp = MagicMock()
        job_id = url.rsplit("/", 1)[-1]
        if url.endswith("/job-posts/public/pages"):
            resp.status_code = 200
            resp.json.return_value = page
        elif job_id in details and detail_status == 200:
            resp.status_code = 200
            resp.json.return_value = details[job_id]
        else:
            resp.status_code = detail_status
        return resp

    mock_client.get = AsyncMock(side_effect=get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_inhire_scan_parses_published_jobs_only():
    mock_client = _make_inhire_client()
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await InHireScanner().scan(["alice"])

    assert [j.title for j in jobs] == ["Design l Creative Design", "Backend Engineer"]
    assert jobs[0].source == "inhire"
    assert jobs[0].company == "alice"
    # Slug derived from displayName: without it the SPA renders a black screen
    # (verified live 2026-08-21, both jobs, incognito included).
    assert jobs[0].url == (
        "https://alice.inhire.app/vagas/832b18f4-adf6-4c32-8e1b-18321e0b8069"
        "/design-l-creative-design"
    )
    assert jobs[0].remote_type == "hybrid"
    assert jobs[1].remote_type == "remote"
    # Description now comes from the public detail endpoint (re-verified live
    # 2026-08-24: HTTP 200, no auth — the old "403" docstring was stale),
    # HTML stripped like _fetch_description does.
    assert jobs[0].description == "Craft visual systems."
    assert jobs[1].description == "Build APIs in Python."


async def test_inhire_detail_failure_keeps_the_listing_job():
    # One broken detail must not cost the posting — it degrades to the old
    # behavior (description None → needs_review), never drops the job.
    mock_client = _make_inhire_client(detail_status=500)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await InHireScanner().scan(["alice"])
    assert [j.description for j in jobs] == [None, None]
    assert len(jobs) == 2


async def test_inhire_detail_wrong_shape_degrades_to_no_description():
    # Valid JSON that isn't an object (the API answering with a list) must
    # degrade exactly like an HTTP failure: keep the job, description None.
    details = {"832b18f4-adf6-4c32-8e1b-18321e0b8069": ["not", "a", "dict"], "aaaa": ["nope"]}
    mock_client = _make_inhire_client(details=details)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await InHireScanner().scan(["alice"])
    assert [j.description for j in jobs] == [None, None]


def test_inhire_slug_reproduces_the_measured_pipe_case():
    # The one canonical example measured live (2026-08-21):
    # "Senior Elixir Engineer | Plataform" → senior-elixir-engineer-or-plataform
    from moonlighter.discovery.sources.http import _inhire_slug

    assert (
        _inhire_slug("Senior Elixir Engineer | Plataform") == "senior-elixir-engineer-or-plataform"
    )
    assert _inhire_slug("Analista Sênior de Facilities & Compras") == (
        "analista-senior-de-facilities-compras"
    )


async def test_inhire_sends_the_tenant_header():
    mock_client = _make_mock_client(INHIRE_PAGE)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        await InHireScanner().scan(["alice"])
    first = mock_client.get.call_args_list[0]
    assert first.kwargs["headers"]["X-Tenant"] == "alice"
    assert first.args[0] == "https://api.inhire.app/job-posts/public/pages"
    # Every detail call carries the tenant header too — the API 403s without it.
    for call in mock_client.get.call_args_list[1:]:
        assert call.kwargs["headers"]["X-Tenant"] == "alice"


async def test_inhire_wrong_shape_counts_as_error():
    mock_client = _make_mock_client(["not", "a", "dict"])
    stats = {}
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await InHireScanner().scan(["alice"], stats=stats)
    assert jobs == []
    assert stats["inhire"].errors == 1


def test_inhire_is_a_listing_source_for_staleness():
    from moonlighter.discovery.sources.registry import LISTING_SOURCES

    assert "inhire" in LISTING_SOURCES


async def test_inhire_non_list_jobs_page_counts_as_error():
    mock_client = _make_mock_client({"tenantName": "Alice", "jobsPage": "oops"})
    stats = {}
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=mock_client):
        jobs = await InHireScanner().scan(["alice"], stats=stats)
    assert jobs == []
    assert stats["inhire"].errors == 1
