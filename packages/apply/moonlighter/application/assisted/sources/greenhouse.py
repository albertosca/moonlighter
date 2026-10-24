"""Greenhouse publishes the whole application form on its board API.

`GET /v1/boards/{board}/jobs/{id}?questions=true` returns every question with its
label, whether it is required, its widget type and — for selects — the exact
options. Verified against a live posting on 2026-08-11.
"""

import re
from typing import Any

import httpx
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sources.base import SourceMatch, yes_no_question
from moonlighter.core.db import Job

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?questions=true"
HEADERS = {"User-Agent": "moonlighter/0.1"}

_URL = re.compile(r"greenhouse\.io/(?P<board>[^/]+)/jobs/(?P<job_id>\d+)")

# Anything not listed becomes LONG_TEXT: an unknown widget must still reach the
# human, and LONG_TEXT is the conservative side of the one behavioural
# difference between the two free-text kinds — TEXT is eligible for the
# cross-job answer bank, LONG_TEXT never is. They render and prompt identically.
_KINDS = {
    "input_text": QuestionKind.TEXT,
    "textarea": QuestionKind.LONG_TEXT,
    "input_file": QuestionKind.FILE,
    "multi_value_single_select": QuestionKind.SINGLE_SELECT,
    "multi_value_multi_select": QuestionKind.MULTI_SELECT,
    "boolean": QuestionKind.BOOLEAN,
}


def board_and_job_from_url(url: str) -> tuple[str, str] | None:
    match = _URL.search(url)
    return (match["board"], match["job_id"]) if match else None


def _options(field: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(value["label"])
        for value in field.get("values") or []
        if isinstance(value, dict) and value.get("label")
    )


def parse_greenhouse_questions(payload: dict[str, Any]) -> list[FormQuestion]:
    questions: list[FormQuestion] = []
    for item in payload.get("questions") or []:
        label = item.get("label")
        if not label:
            continue
        fields = item.get("fields") or [{}]
        field = fields[0]
        kind = _KINDS.get(str(field.get("type")), QuestionKind.LONG_TEXT)
        options = _options(field)
        # A `boolean` is a Yes/No question, one shape whatever the source
        # (2026-09-29); its `values` carry the labels the page shows. Never seen
        # live: 80 postings over 10 boards (2026-10-05) asked Yes/No questions as
        # multi_value_single_select.
        if kind is QuestionKind.BOOLEAN:
            questions.append(yes_no_question(str(label), bool(item.get("required")), options))
            continue
        # A select whose options did not come through cannot be answered as a
        # select; degrade to free text so the question still reaches the human —
        # to LONG_TEXT, the bank-ineligible one, for the reason given above the
        # _KINDS table: an unknown shape must not become a reusable answer.
        if kind in (QuestionKind.SINGLE_SELECT, QuestionKind.MULTI_SELECT) and not options:
            kind = QuestionKind.LONG_TEXT
        questions.append(
            FormQuestion(
                label=str(label),
                kind=kind,
                required=bool(item.get("required")),
                options=options,
            )
        )
    return questions


async def fetch_greenhouse_questions(
    board: str, job_id: str, client: httpx.AsyncClient
) -> list[FormQuestion]:
    response = await client.get(API.format(board=board, job_id=job_id), headers=HEADERS)
    if response.status_code != 200:
        return []
    payload = response.json()
    return parse_greenhouse_questions(payload) if isinstance(payload, dict) else []


class GreenhouseSource:
    name = "greenhouse"

    def match(self, job: Job) -> SourceMatch | None:
        # Keyed on the URL, not job.source: add_job stores source='manual' even
        # for a recognizable Greenhouse URL, and the regex demands a
        # greenhouse.io host, so a false positive cannot happen.
        found = board_and_job_from_url(job.url)
        return SourceMatch(self, found) if found else None

    async def questions(self, match: SourceMatch, client: httpx.AsyncClient) -> list[FormQuestion]:
        board, job_id = match.locator
        return await fetch_greenhouse_questions(board, job_id, client)

    async def required_fields(
        self, match: SourceMatch, client: httpx.AsyncClient
    ) -> tuple[str, ...]:
        return ()
