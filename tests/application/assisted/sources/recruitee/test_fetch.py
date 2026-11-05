"""Recognising a Recruitee offer URL and fetching its questions."""

import httpx
import pytest

from moonlighter.application.assisted.sources.recruitee import (
    fetch_recruitee_questions,
    host_and_offer_from_url,
    parse_recruitee_questions,
)
from tests.application.assisted.sources.recruitee.recruitee_offers import PAYLOAD


def test_host_and_offer_are_read_from_a_recruitee_url():
    assert host_and_offer_from_url("https://curotec.recruitee.com/o/senior-android/c/new") == (
        "curotec.recruitee.com",
        "senior-android",
    )


def test_a_custom_career_domain_is_matched_too():
    # Most Recruitee customers use their own domain, and it serves the same
    # offers API (proven by the discovery scanner, wave A). Safe here because
    # the service routes to this source only when job.source == "recruitee".
    assert host_and_offer_from_url("https://jobs.channable.com/o/x") == (
        "jobs.channable.com",
        "x",
    )


def test_a_non_offer_path_is_not_matched():
    assert host_and_offer_from_url("https://careers.acme.com/jobs/engineer") is None


@pytest.mark.asyncio
async def test_a_failed_request_yields_no_questions():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_recruitee_questions("curotec", "x", client) == []


@pytest.mark.asyncio
async def test_a_successful_request_returns_the_parsed_questions():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=PAYLOAD)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        questions = await fetch_recruitee_questions("curotec", "x", client)
    assert questions == parse_recruitee_questions(PAYLOAD)
