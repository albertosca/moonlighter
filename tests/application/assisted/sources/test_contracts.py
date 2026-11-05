"""Pins for the wire-level contracts of the form-question sources and the paste reader."""

import hashlib
import json
import logging
from typing import Any

import httpx
import pytest

from moonlighter.application.assisted.questions import FormQuestion
from moonlighter.application.assisted.sources import base, pasted
from moonlighter.application.assisted.sources.base import (
    SourceMatch,
    questions_or_empty,
    required_fields_or_empty,
)
from moonlighter.application.assisted.sources.greenhouse import fetch_greenhouse_questions
from moonlighter.application.assisted.sources.inhire import fetch_inhire_required_fields
from moonlighter.application.assisted.sources.lever import fetch_lever_questions, parse_lever_form
from moonlighter.application.assisted.sources.pasted import (
    ExtractionError,
    extract_questions_from_page,
)
from moonlighter.application.assisted.sources.recruitee import fetch_recruitee_questions
from moonlighter.application.assisted.sources.workable import fetch_workable_questions

PROMPT_DIGEST = "a5286adec69fb7cfefc35f2a2e017e192487f4c829f6806bb206cadb7fdc6c26"
LANGUAGE_TABLES_DIGEST = "cb03dfb25d4f041dd8f54ba0d1a4d976d92213657f6de2929ac156e139db8060"
JOB_ID = "1a3ea3dc-5558-45b6-aecb-58e89f5af1dd"


async def _request_seen_by(fetch: Any, *arguments: str) -> httpx.Request:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await fetch(*arguments, client)
    [request] = seen
    return request


@pytest.mark.parametrize(
    ("fetch", "arguments", "url", "user_agent"),
    [
        (
            fetch_greenhouse_questions,
            ("acme", "7"),
            "https://boards-api.greenhouse.io/v1/boards/acme/jobs/7?questions=true",
            "moonlighter/0.1",
        ),
        (
            fetch_inhire_required_fields,
            ("infleet", JOB_ID),
            f"https://api.inhire.app/job-posts/public/pages/{JOB_ID}",
            "moonlighter/0.1",
        ),
        (
            fetch_lever_questions,
            ("acme", "abc"),
            "https://jobs.lever.co/acme/abc/apply",
            "Mozilla/5.0 (compatible; moonlighter/0.1)",
        ),
        (
            fetch_recruitee_questions,
            ("acme.recruitee.com", "engineer"),
            "https://acme.recruitee.com/api/offers/engineer",
            "moonlighter/0.1",
        ),
        (
            fetch_workable_questions,
            ("ABC123",),
            "https://apply.workable.com/api/v1/jobs/ABC123/form",
            "moonlighter/0.1",
        ),
    ],
)
async def test_each_source_asks_its_own_url_and_names_itself(fetch, arguments, url, *, user_agent):
    request = await _request_seen_by(fetch, *arguments)
    assert str(request.url) == url
    assert request.headers["User-Agent"] == user_agent


def test_the_lever_parser_converts_character_references_in_labels():
    page = (
        '<li class="application-question"><div class="application-label">'
        "Caf&eacute; &amp; Bar</div></li>"
    )
    assert [question.label for question in parse_lever_form(page)] == ["Café & Bar"]


class _FailingSource:
    name = "failing"

    async def questions(self, match: SourceMatch, client: httpx.AsyncClient) -> list[FormQuestion]:
        raise RuntimeError("boom")

    async def required_fields(
        self, match: SourceMatch, client: httpx.AsyncClient
    ) -> tuple[str, ...]:
        raise RuntimeError("bang")


async def test_a_failing_source_is_logged_with_its_traceback(caplog):
    match = SourceMatch(_FailingSource(), ())  # type: ignore[arg-type]  # a duck-typed fake source
    async with httpx.AsyncClient() as client:
        with caplog.at_level(logging.WARNING, logger=base.logger.name):
            assert await questions_or_empty(match, client) == []
            assert await required_fields_or_empty(match, client) == ()
    questions_record, fields_record = caplog.records
    assert questions_record.getMessage() == "failing questions unavailable: boom"
    assert fields_record.getMessage() == "failing required fields unavailable: bang"
    assert questions_record.exc_info is not None
    assert fields_record.exc_info is not None


def test_the_prompt_text_is_frozen():
    assert hashlib.sha256(pasted.PROMPT.encode()).hexdigest() == PROMPT_DIGEST


def test_the_language_tables_are_frozen():
    tables = {
        "markers": {language: sorted(words) for language, words in base._LANGUAGE_MARKERS.items()},
        "answers": {language: list(words) for language, words in base._YES_NO_BY_LANGUAGE.items()},
    }
    dumped = json.dumps(tables, sort_keys=True, ensure_ascii=False).encode()
    assert hashlib.sha256(dumped).hexdigest() == LANGUAGE_TABLES_DIGEST


async def test_the_page_is_capped_at_twenty_thousand_characters():
    prompts: list[str] = []

    async def call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        prompts.append(prompt)
        return '{"questions": []}'

    await extract_questions_from_page("a" * 20000 + "b" * 5, call)
    assert "a" * 20000 in prompts[0]
    assert "bbbbb" not in prompts[0]


async def test_the_default_model_is_sonnet():
    models: list[str] = []

    async def call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        models.append(model)
        return '{"questions": []}'

    await extract_questions_from_page("page", call)
    assert models == ["claude-sonnet-4-6"]


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ("x" * 400, "the model's reply was not JSON: "),
        (json.dumps(["y" * 400]), "the model's reply was not a JSON object: "),
    ],
)
async def test_an_unusable_reply_is_quoted_up_to_three_hundred_characters(reply, reason):
    async def call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return reply

    with pytest.raises(ExtractionError) as raised:
        await extract_questions_from_page("page", call)
    assert str(raised.value) == f"{reason}{reply[:300]!r}"
