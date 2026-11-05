"""Lever's remote type and location: what the text says, the workplace field, and every listed place."""

from unittest.mock import patch

import pytest
from moonlighter.discovery.sources.company_boards.lever import LeverScanner

from tests.discovery.sources.fake_http_clients import make_mock_client


# remote_type from the structured workplace field (BACKLOG bug 2026-10-15)
def _lever_posting(*, location, workplace_type=None):
    posting = {
        "id": "abc",
        "text": "Engineer",
        "hostedUrl": "https://jobs.lever.co/co/abc",
        "categories": {"location": location},
    }
    if workplace_type is not None:
        posting["workplaceType"] = workplace_type
    return posting


async def _lever_remote_type(posting):
    mock_client = make_mock_client([posting])
    with patch(
        "moonlighter.discovery.sources.company_boards.lever.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await LeverScanner().scan(["co"])
    return jobs[0].remote_type


@pytest.mark.parametrize(
    ("location", "workplace_type", "expected"),
    [
        ("San Francisco", "onsite", "onsite"),
        ("London", "hybrid", "hybrid"),
        ("Anywhere", "remote", "remote"),
        ("San Francisco", "unspecified", None),
        ("San Francisco", None, None),
        # Explicit text wins over the API: a live Lever board (shieldai) says
        # "Remote" in the location and `onsite` in workplaceType. Trusting the
        # API there would archive a remote job outside the home city.
        ("Remote", "onsite", "remote"),
        ("Hybrid - Berlin", "onsite", "hybrid"),
    ],
)
async def test_lever_remote_type_fills_from_workplace_type_only_when_text_is_silent(
    location, workplace_type, expected
):
    posting = _lever_posting(location=location, workplace_type=workplace_type)
    assert await _lever_remote_type(posting) == expected


async def test_lever_location_lists_every_place_and_remote_among_them_wins():
    posting = _lever_posting(location="San Francisco", workplace_type="onsite")
    posting["categories"]["allLocations"] = ["San Francisco", "Remote (US)", "Toronto"]
    mock_client = make_mock_client([posting])
    with patch(
        "moonlighter.discovery.sources.company_boards.lever.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await LeverScanner().scan(["co"])
    assert jobs[0].location == "San Francisco; Remote (US); Toronto"
    # A remote option among the places is a statement the text makes, so it beats
    # the API's onsite instead of letting a hard archive decide without the LLM.
    assert jobs[0].remote_type == "remote"


async def test_lever_without_all_locations_keeps_the_primary_only():
    posting = _lever_posting(location="Berlin", workplace_type="hybrid")
    mock_client = make_mock_client([posting])
    with patch(
        "moonlighter.discovery.sources.company_boards.lever.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await LeverScanner().scan(["co"])
    assert jobs[0].location == "Berlin"
    assert jobs[0].remote_type == "hybrid"
