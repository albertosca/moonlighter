"""How the Workable scanner maps postings and survives failed or malformed board responses."""

from unittest.mock import patch

import httpx
from moonlighter.discovery.sources.company_boards.workable import WorkableScanner

from tests.discovery.sources.fake_http_clients import make_mock_client

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
    mock_client = make_mock_client(WORKABLE_RESPONSE)
    with patch(
        "moonlighter.discovery.sources.company_boards.workable.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WorkableScanner().scan(["acme"])
    assert len(jobs) == 1
    scanned_job = jobs[0]
    assert scanned_job.source == "workable"
    assert scanned_job.company == "acme"
    assert scanned_job.title == "Staff Engineer"
    assert scanned_job.url == "https://apply.workable.com/j/ABC123/apply"
    assert scanned_job.location == "Lisbon, Portugal"
    assert scanned_job.remote_type == "remote"  # telecommuting True wins over location
    assert scanned_job.description == "Build  things"


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
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.workable.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_skips_entry_without_url():
    response = {"jobs": [{"title": "Eng", "shortcode": "X", "application_url": ""}]}
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.workable.httpx.AsyncClient",
        return_value=mock_client,
    ):
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
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.workable.httpx.AsyncClient",
        return_value=mock_client,
    ):
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
    mock_client = make_mock_client(response)
    with patch(
        "moonlighter.discovery.sources.company_boards.workable.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs[0].location is None
    assert jobs[0].remote_type is None


async def test_workable_500_response_skips_company():
    mock_client = make_mock_client({}, status_code=500)
    with patch(
        "moonlighter.discovery.sources.company_boards.workable.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_network_exception_skips_company():
    mock_client = make_mock_client(raise_exception=httpx.ConnectError("timeout"))
    with patch(
        "moonlighter.discovery.sources.company_boards.workable.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_non_dict_response_returns_empty():
    mock_client = make_mock_client([{"title": "Eng"}])
    with patch(
        "moonlighter.discovery.sources.company_boards.workable.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []


async def test_workable_missing_jobs_key_returns_empty():
    mock_client = make_mock_client({"name": "Acme"})
    with patch(
        "moonlighter.discovery.sources.company_boards.workable.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WorkableScanner().scan(["acme"])
    assert jobs == []
