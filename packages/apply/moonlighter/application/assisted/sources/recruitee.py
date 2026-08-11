"""Recruitee publishes its custom questions on the public offer API.

`GET /api/offers/{offer}` nests everything under `offer`, and carries
`open_questions`, `dynamic_fields` and a separate location question. Verified
against a live posting on 2026-08-11. Only `<slug>.recruitee.com` is matched:
most customers use their own domain, and those go through pasting.

`options` on a question is always an empty dict on live data, whatever the
question's kind — it is not where the choices live. A `multi_choice`
question's actual alternatives are a *sibling* list, `open_question_options`,
each entry carrying its own `body` and `position`.
"""

import re
from typing import Any

import httpx
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind

API = "https://{slug}.recruitee.com/api/offers/{offer}"
HEADERS = {"User-Agent": "moonlighter/0.1"}

_URL = re.compile(r"https?://(?P<slug>[\w-]+)\.recruitee\.com/o/(?P<offer>[\w-]+)")

# `multi_choice` is handled separately, since its options live in a sibling
# list rather than being a fixed kind->QuestionKind mapping. Anything not
# listed here and not `multi_choice` is an unrecognised kind: it still
# reaches the human as free text rather than vanishing.
_SIMPLE_KINDS = {
    "boolean": QuestionKind.BOOLEAN,
    "date": QuestionKind.TEXT,
}


def slug_and_offer_from_url(url: str) -> tuple[str, str] | None:
    match = _URL.search(url)
    return (match["slug"], match["offer"]) if match else None


def _choice_options(item: dict[str, Any]) -> tuple[str, ...]:
    entries = [
        e for e in item.get("open_question_options") or [] if isinstance(e, dict) and e.get("body")
    ]
    entries.sort(key=lambda e: e.get("position", 0))
    return tuple(str(e["body"]) for e in entries)


def _question(item: dict[str, Any]) -> FormQuestion | None:
    label = item.get("body") or item.get("label")
    if not label:
        return None
    kind_str = str(item.get("kind") or "")
    options: tuple[str, ...] = ()
    if kind_str == "multi_choice":
        options = _choice_options(item)
        kind = QuestionKind.SINGLE_SELECT if options else QuestionKind.TEXT
    elif kind_str in _SIMPLE_KINDS:
        kind = _SIMPLE_KINDS[kind_str]
    elif kind_str:
        kind = QuestionKind.TEXT
    else:
        # No kind info at all: a plain open question, answered in free text.
        kind = QuestionKind.LONG_TEXT
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
