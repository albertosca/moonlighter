"""Recruitee publishes its custom questions on the public offer API.

`GET /api/offers/{offer}` nests everything under `offer`, and carries
`open_questions`, `dynamic_fields` and a separate location question. Verified
against a live posting on 2026-08-11. Only `<slug>.recruitee.com` is matched:
most customers use their own domain, and those go through pasting.
"""

import re
from typing import Any

import httpx
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

API = "https://{slug}.recruitee.com/api/offers/{offer}"
HEADERS = {"User-Agent": "moonlighter/0.1"}

_URL = re.compile(r"https?://(?P<slug>[\w-]+)\.recruitee\.com/o/(?P<offer>[\w-]+)")


def slug_and_offer_from_url(url: str) -> tuple[str, str] | None:
    match = _URL.search(url)
    return (match["slug"], match["offer"]) if match else None


def _question(item: dict[str, Any]) -> FormQuestion | None:
    label = item.get("body") or item.get("label")
    if not label:
        return None
    options = tuple(str(o) for o in item.get("options") or [])
    kind = QuestionKind.LONG_TEXT
    if "choice" in str(item.get("kind", "")):
        kind = QuestionKind.SINGLE_SELECT if options else QuestionKind.TEXT
    return FormQuestion(
        label=str(label),
        kind=kind,
        required=bool(item.get("required")),
        options=options if kind is QuestionKind.SINGLE_SELECT else (),
    )


def parse_recruitee_questions(payload: dict[str, Any]) -> list[FormQuestion]:
    offer = payload.get("offer") or {}
    questions: list[FormQuestion] = []

    for item in [*(offer.get("open_questions") or []), *(offer.get("dynamic_fields") or [])]:
        if isinstance(item, dict) and (question := _question(item)) is not None:
            questions.append(question)

    location_label = offer.get("locations_question")
    if location_label:
        questions.append(
            FormQuestion(
                label=str(location_label),
                kind=QuestionKind.TEXT,
                required=bool(offer.get("locations_question_required")),
            )
        )
    return questions


async def fetch_recruitee_questions(
    slug: str, offer: str, client: httpx.AsyncClient
) -> list[FormQuestion]:
    response = await client.get(API.format(slug=slug, offer=offer), headers=HEADERS)
    if response.status_code != 200:
        return []
    payload = response.json()
    return parse_recruitee_questions(payload) if isinstance(payload, dict) else []
