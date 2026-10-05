"""Recruitee publishes its custom questions on the public offer API.

`GET /api/offers/{offer}` nests everything under `offer`, and carries
`open_questions`, `dynamic_fields` and a separate location question. Verified
against a live posting on 2026-08-11. Custom career domains (jobs.example.com)
serve the same offers API on their own host — proven by the discovery scanner
(wave A) — so the offer URL's host is used verbatim. The /o/ pattern alone
would match any site, which is why the service only routes here when
job.source == "recruitee".

`options` on a question is always an empty dict on live data, whatever the
question's kind — it is not where the choices live. A `multi_choice`
question's actual alternatives are a *sibling* list, `open_question_options`,
each entry carrying its own `body` and `position`.
"""

import re
from typing import Any

import httpx
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sources.base import (
    SourceMatch,
    is_question,
    yes_no_question,
)
from moonlighter.core.db import Job

API = "https://{host}/api/offers/{offer}"
HEADERS = {"User-Agent": "moonlighter/0.1"}

_URL = re.compile(r"https?://(?P<host>[^/]+)/o/(?P<offer>[\w-]+)")

# `multi_choice` is handled separately, since its options live in a sibling
# list rather than being a fixed kind->QuestionKind mapping. Anything not
# listed here and not `multi_choice` is an unrecognised kind: it still
# reaches the human as free text rather than vanishing — as LONG_TEXT, which
# unlike TEXT is never eligible for the cross-job answer bank. The two render
# and prompt identically, so a question whose shape we could not read degrades
# to the side that is never replayed at a different company.
_SIMPLE_KINDS = {
    "boolean": QuestionKind.BOOLEAN,
    "date": QuestionKind.TEXT,
}

# The offers API publishes only the *custom* questions; the standard candidate
# fields are declared by options_* flags ("required" | "optional" | "off") on
# the offer instead. A sheet without them claims completeness over a form that
# still wants name, email and a CV — and gives the tracking alias no email
# question to land on (found live on the Curotec gate application, 2026-08-13).
# Name and email carry no flag: every Recruitee form asks them.
_STANDARD_FLAGS = (
    ("options_phone", "Phone", QuestionKind.TEXT),
    ("options_photo", "Photo", QuestionKind.FILE),
    ("options_cv", "CV", QuestionKind.FILE),
    ("options_cover_letter", "Cover letter", QuestionKind.LONG_TEXT),
)


def _standard_fields(offer: dict[str, Any]) -> list[FormQuestion]:
    questions = [
        FormQuestion(label="Full name", kind=QuestionKind.TEXT, required=True),
        FormQuestion(label="Email", kind=QuestionKind.TEXT, required=True),
    ]
    for flag, label, kind in _STANDARD_FLAGS:
        value = str(offer.get(flag) or "off")
        if value != "off":
            questions.append(FormQuestion(label=label, kind=kind, required=value == "required"))
    return questions


def host_and_offer_from_url(url: str) -> tuple[str, str] | None:
    match = _URL.search(url)
    return (match["host"], match["offer"]) if match else None


def _choice_options(item: dict[str, Any]) -> tuple[str, ...]:
    entries = [
        entry
        for entry in item.get("open_question_options") or []
        if isinstance(entry, dict) and entry.get("body")
    ]
    entries.sort(key=lambda entry: entry.get("position", 0))
    return tuple(str(entry["body"]) for entry in entries)


def _question(item: dict[str, Any]) -> FormQuestion | None:
    label = item.get("body") or item.get("label")
    if not label:
        return None
    kind_name = str(item.get("kind") or "")
    # How Recruitee renders `boolean` was never observed live, so the paste
    # path's rule decides: a question becomes the Yes/No single_select every
    # source gives (2026-09-29), a statement to tick (consent) stays boolean.
    if kind_name == "boolean" and is_question(str(label)):
        return yes_no_question(str(label), bool(item.get("required")))
    options: tuple[str, ...] = ()
    if kind_name == "multi_choice":
        options = _choice_options(item)
        kind = QuestionKind.SINGLE_SELECT if options else QuestionKind.LONG_TEXT
    elif kind_name in _SIMPLE_KINDS:
        kind = _SIMPLE_KINDS[kind_name]
    elif kind_name:
        kind = QuestionKind.LONG_TEXT
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
    offer = payload.get("offer")
    if not isinstance(offer, dict):
        # A 200 without an offer object is a malformed payload, not a form with
        # zero questions — returning [] keeps the paste-hint path reachable
        # instead of producing a phantom name+email sheet.
        return []
    questions: list[FormQuestion] = _standard_fields(offer)

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
    host: str, offer: str, client: httpx.AsyncClient
) -> list[FormQuestion]:
    response = await client.get(API.format(host=host, offer=offer), headers=HEADERS)
    if response.status_code != 200:
        return []
    payload = response.json()
    return parse_recruitee_questions(payload) if isinstance(payload, dict) else []


class RecruiteeSource:
    name = "recruitee"

    def match(self, job: Job) -> SourceMatch | None:
        # Source-gated: the /o/ pattern alone would match any site.
        if job.source != "recruitee":
            return None
        found = host_and_offer_from_url(job.url)
        return SourceMatch(self, found) if found else None

    async def questions(self, match: SourceMatch, client: httpx.AsyncClient) -> list[FormQuestion]:
        host, offer = match.locator
        return await fetch_recruitee_questions(host, offer, client)

    async def required_fields(
        self, match: SourceMatch, client: httpx.AsyncClient
    ) -> tuple[str, ...]:
        return ()
