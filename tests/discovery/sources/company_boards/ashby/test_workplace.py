"""Ashby's remote type and location: the remote flag, the workplace field, and secondary locations."""

from unittest.mock import patch

import pytest

from moonlighter.discovery.sources.company_boards.ashby import AshbyScanner
from tests.discovery.sources.company_boards.ashby.fake_board import ASHBY_JOB, ashby_response
from tests.discovery.sources.fake_http_clients import make_mock_client


@pytest.mark.parametrize(
    ("location", "is_remote", "workplace_type", "expected"),
    [
        ("Berlin", False, "OnSite", "onsite"),
        ("Berlin", False, "Hybrid", "hybrid"),
        ("Anywhere", False, "Remote", "remote"),
        ("Berlin", False, None, None),
        ("Berlin", False, "Unknown", None),
        ("Hybrid - NYC", False, "OnSite", "hybrid"),  # text wins
        ("Berlin", True, "OnSite", "remote"),  # isRemote keeps its precedence
    ],
)
async def test_ashby_remote_type_fills_from_workplace_type_only_when_text_is_silent(
    *, location, is_remote, workplace_type, expected
):
    job = {**ASHBY_JOB, "location": location, "isRemote": is_remote}
    if workplace_type is not None:
        job["workplaceType"] = workplace_type
    mock_client = make_mock_client(ashby_response(job))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs[0].remote_type == expected


async def test_ashby_location_lists_secondary_locations_and_remote_wins():
    job = {
        **ASHBY_JOB,
        "location": "San Francisco",
        "isRemote": False,
        "workplaceType": "OnSite",
        "secondaryLocations": [{"location": "Remote"}, {"location": "Toronto"}, {"location": ""}],
    }
    mock_client = make_mock_client(ashby_response(job))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs[0].location == "San Francisco; Remote; Toronto"
    assert jobs[0].remote_type == "remote"


async def test_ashby_malformed_secondary_locations_fall_back_to_the_primary():
    job = {**ASHBY_JOB, "location": "Berlin", "isRemote": False, "secondaryLocations": "oops"}
    mock_client = make_mock_client(ashby_response(job))
    with patch(
        "moonlighter.discovery.sources.company_boards.ashby.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await AshbyScanner().scan(["co"])
    assert jobs[0].location == "Berlin"
