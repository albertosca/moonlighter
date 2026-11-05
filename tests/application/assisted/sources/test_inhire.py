import json

import httpx
from moonlighter.application.assisted.sources.base import SourceMatch
from moonlighter.application.assisted.sources.inhire import (
    InHireSource,
    fetch_inhire_required_fields,
    parse_required_fields,
    tenant_and_job_from_url,
)

from tests.application.assisted.sources.fixture_files import FIXTURES_DIRECTORY

DETAIL = json.loads((FIXTURES_DIRECTORY / "inhire_job_infleet.json").read_text())
JOB_ID = "1a3ea3dc-5558-45b6-aecb-58e89f5af1dd"


def test_required_ids_become_readable_labels():
    assert parse_required_fields(DETAIL) == ("LinkedIn", "Salary expectation", "CV")


def test_an_unknown_required_id_passes_through_verbatim():
    assert parse_required_fields({"settings": {"requiredFields": ["location", "cpf"]}}) == (
        "Location",
        "cpf",
    )
    assert parse_required_fields({"settings": {"requiredFields": ["", "linkedin"]}}) == (
        "LinkedIn",
    )


def test_an_object_shaped_required_entry_uses_its_id_or_name():
    # Probed in the final review: a dict entry rendered as "{'id': 'linkedin'}".
    payload = {"settings": {"requiredFields": [{"id": "linkedin"}, {"name": "cpf"}, {"other": 1}]}}
    assert parse_required_fields(payload) == ("LinkedIn", "cpf")


def test_a_payload_without_required_fields_has_none():
    assert parse_required_fields({"settings": {}}) == ()
    assert parse_required_fields({"settings": {"requiredFields": "linkedin"}}) == ()
    assert parse_required_fields(["not", "a", "dict"]) == ()


def test_tenant_and_job_from_url_demands_a_real_uuid():
    assert tenant_and_job_from_url(f"https://infleet.inhire.app/vagas/{JOB_ID}0") is None
    assert tenant_and_job_from_url("https://infleet.inhire.app/vagas/" + "a" * 36) is None
    assert tenant_and_job_from_url(f"https://infleet.inhire.app/vagas/{JOB_ID}/candidatura") == (
        "infleet",
        JOB_ID,
    )


def test_tenant_and_job_from_url():
    assert tenant_and_job_from_url(f"https://infleet.inhire.app/vagas/{JOB_ID}") == (
        "infleet",
        JOB_ID,
    )
    assert tenant_and_job_from_url("https://infleet.inhire.app/sobre") is None


async def test_fetch_sends_the_tenant_header():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("X-Tenant")))
        return httpx.Response(200, json=DETAIL)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_inhire_required_fields("infleet", JOB_ID, client) == (
            "LinkedIn",
            "Salary expectation",
            "CV",
        )
    assert seen == [(f"https://api.inhire.app/job-posts/public/pages/{JOB_ID}", "infleet")]


async def test_a_non_200_has_no_required_fields(caplog):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(404))
    ) as client:
        assert await fetch_inhire_required_fields("infleet", JOB_ID, client) == ()
    [record] = [
        record
        for record in caplog.records
        if record.name == "moonlighter.application.assisted.sources.inhire"
    ]
    assert record.levelname == "WARNING"
    assert "404" in record.getMessage()


async def test_inhire_never_claims_to_have_the_questions():
    # InHire publishes no questions before an application is submitted, so the
    # source must not even ask: any request here is a bug, not just a 500.
    requests_made: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests_made.append(request)
        return httpx.Response(200, json={"questions": [{"label": "Q"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(record)) as client:
        source = InHireSource()
        assert await source.questions(SourceMatch(source, ("infleet", JOB_ID)), client) == []
    assert requests_made == []


async def test_inhire_source_required_fields_delegates_to_the_fetch():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=DETAIL))
    ) as client:
        source = InHireSource()
        match = SourceMatch(source, ("infleet", JOB_ID))
        assert await source.required_fields(match, client) == (
            "LinkedIn",
            "Salary expectation",
            "CV",
        )
