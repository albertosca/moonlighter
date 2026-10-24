"""Workable publishes the application form on the endpoint its own apply page calls.

`GET https://apply.workable.com/api/v1/jobs/{shortcode}/form` returns a list of
sections, each `{"name", "fields"}`; every field carries `label`, `type` and
`required`, and choices carry `options` as `{"name", "value"}`. Undocumented —
verified against live postings on 2026-09-25 (bancada ats-form-apis). Custom
career domains were never observed, so only apply.workable.com URLs match.
"""

import logging
import re
from typing import Any

import httpx
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sources.base import SourceMatch, yes_no_question
from moonlighter.core.db import Job

API = "https://apply.workable.com/api/v1/jobs/{shortcode}/form"
HEADERS = {"User-Agent": "moonlighter/0.1"}

logger = logging.getLogger(__name__)

_URL = re.compile(r"apply\.workable\.com/(?:[^/]+/)?j/(?P<shortcode>[A-Za-z0-9]+)")

# Anything not listed becomes LONG_TEXT (see greenhouse.py for why that side).
# `group` (Education/Experience) nests sub-fields; it reaches the human as one
# free-text question under its own label rather than being guessed apart.
# `boolean` is Workable's Yes/No question type: the page renders YES/NO buttons
# whatever the label's grammar (Seeq, live 2026-10-05; a Devsu label reads
# "Selecting 'No' means..."), never a lone tick box — so every one becomes the
# Yes/No single_select, as Lever and paste give the same questions.
_KINDS = {
    "text": QuestionKind.TEXT,
    "email": QuestionKind.TEXT,
    "phone": QuestionKind.TEXT,
    "number": QuestionKind.TEXT,
    "paragraph": QuestionKind.LONG_TEXT,
    "file": QuestionKind.FILE,
    "boolean": QuestionKind.BOOLEAN,
    "dropdown": QuestionKind.SINGLE_SELECT,
}
_CHOICE_KINDS = (QuestionKind.SINGLE_SELECT, QuestionKind.MULTI_SELECT)


def shortcode_from_url(url: str) -> str | None:
    match = _URL.search(url)
    return match["shortcode"] if match else None


def _kind(field: dict[str, Any]) -> QuestionKind:
    field_type = str(field.get("type"))
    if field_type == "multiple":
        return (
            QuestionKind.SINGLE_SELECT if field.get("singleOption") else QuestionKind.MULTI_SELECT
        )
    return _KINDS.get(field_type, QuestionKind.LONG_TEXT)


def _options(field: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(option["value"])
        for option in field.get("options") or []
        if isinstance(option, dict) and option.get("value")
    )


def parse_workable_form(payload: object) -> list[FormQuestion]:
    if not isinstance(payload, list):
        return []
    questions: list[FormQuestion] = []
    for section in payload:
        if not isinstance(section, dict):
            continue
        for field in section.get("fields") or []:
            if not isinstance(field, dict) or not field.get("label"):
                continue
            kind = _kind(field)
            if kind is QuestionKind.BOOLEAN:
                questions.append(
                    yes_no_question(
                        str(field["label"]), bool(field.get("required")), _options(field)
                    )
                )
                continue
            options = _options(field) if kind in _CHOICE_KINDS else ()
            if kind in _CHOICE_KINDS and not options:
                kind = QuestionKind.LONG_TEXT
            questions.append(
                FormQuestion(
                    label=str(field["label"]),
                    kind=kind,
                    required=bool(field.get("required")),
                    options=options,
                )
            )
    return questions


async def fetch_workable_questions(shortcode: str, client: httpx.AsyncClient) -> list[FormQuestion]:
    response = await client.get(API.format(shortcode=shortcode), headers=HEADERS)
    if response.status_code != 200:
        logger.warning("workable form for %s unavailable: HTTP %s", shortcode, response.status_code)
        return []
    return parse_workable_form(response.json())


class WorkableSource:
    name = "workable"

    def match(self, job: Job) -> SourceMatch | None:
        shortcode = shortcode_from_url(job.url)
        return SourceMatch(self, (shortcode,)) if shortcode else None

    async def questions(self, match: SourceMatch, client: httpx.AsyncClient) -> list[FormQuestion]:
        (shortcode,) = match.locator
        return await fetch_workable_questions(shortcode, client)

    async def required_fields(
        self, match: SourceMatch, client: httpx.AsyncClient
    ) -> tuple[str, ...]:
        return ()
