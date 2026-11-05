"""Fetching a Lever apply page and recognising a Lever posting URL."""

import httpx
from moonlighter.application.assisted.sources.base import SourceMatch, questions_or_empty
from moonlighter.application.assisted.sources.lever import (
    LeverSource,
    fetch_lever_questions,
    posting_from_url,
)

from tests.application.assisted.sources.lever.lever_pages import PAGE


async def test_lever_publishes_no_separate_required_fields():
    async with httpx.AsyncClient() as client:
        source = LeverSource()
        assert await source.required_fields(SourceMatch(source, ("a", "b")), client) == ()


def test_posting_from_url_demands_a_real_uuid():
    assert posting_from_url("https://jobs.lever.co/palantir/" + "-" * 36) is None
    uuid = "6ed76ce8-4156-4b60-b120-403538bd66cd"
    assert posting_from_url(f"https://jobs.lever.co/palantir/{uuid}0") is None


def test_posting_from_url():
    uuid = "6ed76ce8-4156-4b60-b120-403538bd66cd"
    assert posting_from_url(f"https://jobs.lever.co/palantir/{uuid}") == ("palantir", uuid)
    assert posting_from_url(f"https://jobs.lever.co/palantir/{uuid}/apply") == ("palantir", uuid)
    assert posting_from_url(f"https://jobs.eu.lever.co/palantir/{uuid}") is None
    assert posting_from_url("https://jobs.lever.co/palantir") is None


async def test_fetch_reads_the_apply_page():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text=PAGE)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        questions = await fetch_lever_questions("palantir", "abc", client)
    assert seen == ["https://jobs.lever.co/palantir/abc/apply"]
    assert questions


async def test_a_non_200_means_no_form(caplog):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(404))
    ) as client:
        assert await fetch_lever_questions("palantir", "abc", client) == []
    [record] = [
        record
        for record in caplog.records
        if record.name == "moonlighter.application.assisted.sources.lever"
    ]
    assert record.levelname == "WARNING"
    assert "404" in record.getMessage()


async def test_a_malformed_card_reaches_the_person_as_the_paste_hint():
    broken = PAGE.replace('name="cards[', 'value="{not json" name="cards[', 1)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=broken))
    ) as client:
        assert (
            await questions_or_empty(SourceMatch(LeverSource(), ("palantir", "abc")), client) == []
        )
