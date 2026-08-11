"""Greenhouse publishes the whole application form on its board API.

`GET /v1/boards/{board}/jobs/{id}?questions=true` returns every question with its
label, whether it is required, its widget type and — for selects — the exact
options. Verified against a live posting on 2026-08-11.
"""

import re
from typing import Any

import httpx
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?questions=true"
HEADERS = {"User-Agent": "moonlighter/0.1"}

_URL = re.compile(r"greenhouse\.io/(?P<board>[^/]+)/jobs/(?P<job_id>\d+)")

# Anything not listed becomes TEXT: an unknown widget must still reach the human.
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
        str(v["label"]) for v in field.get("values") or [] if isinstance(v, dict) and v.get("label")
    )


def parse_greenhouse_questions(payload: dict[str, Any]) -> list[FormQuestion]:
    questions: list[FormQuestion] = []
    for item in payload.get("questions") or []:
        label = item.get("label")
        if not label:
            continue
        fields = item.get("fields") or [{}]
        field = fields[0]
        kind = _KINDS.get(str(field.get("type")), QuestionKind.TEXT)
        options = _options(field)
        # A select whose options did not come through cannot be answered as a
        # select; degrade to text so the question still reaches the human.
        if kind in (QuestionKind.SINGLE_SELECT, QuestionKind.MULTI_SELECT) and not options:
            kind = QuestionKind.TEXT
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
