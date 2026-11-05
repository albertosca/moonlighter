"""Lever has no JSON form API; its public apply page carries the whole form.

`GET https://jobs.lever.co/{company}/{posting}/apply` is HTML (~1.9 MB). Standard
fields are `<li class="application-question">` with a `div.application-label`
whose `<span class="required">✱</span>` marks a required field; the resume
field's `<li>` also has the class `resume`. Custom questions are cards: a hidden
`<input name="cards[<id>][baseTemplate]" value="<HTML-escaped JSON>">` whose
`fields` carry `type`, `text`, `required` and `options[].text`; their `<li>`s
are `custom-question` and are read from the JSON, not the markup. Verified on a
live posting on 2026-09-25 (bancada ats-form-apis). A malformed card makes the
whole form unreadable: a sheet silently missing a card would claim a complete
form. For the same reason the `custom-question` `<li>`s are counted, and a count
that disagrees with the questions read from the cards is markup drift (a renamed
`[baseTemplate]`, a renamed `fields`), never a smaller form. The optional
"Additional information" box — the cover-letter slot — is a
`<textarea name="comments">` outside every question `<li>`, so it is looked for
on its own. jobs.eu.lever.co was never observed and does not match.
"""

import logging
import re
from html.parser import HTMLParser
from typing import override

import httpx

from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sources.base import UUID_PATTERN, SourceMatch
from moonlighter.application.assisted.sources.lever_cards import card_questions
from moonlighter.core.db import Job

APPLY_PAGE = "https://jobs.lever.co/{company}/{posting_id}/apply"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; moonlighter/0.1)"}

logger = logging.getLogger(__name__)

_URL = re.compile(rf"https?://jobs\.lever\.co/(?P<company>[^/]+)/(?P<posting_id>{UUID_PATTERN})")

_REQUIRED_MARK = "✱"
_ADDITIONAL_INFORMATION = FormQuestion(
    label="Additional information", kind=QuestionKind.LONG_TEXT, required=False
)


def posting_from_url(url: str) -> tuple[str, str] | None:
    match = _URL.search(url)
    return (match["company"], match["posting_id"]) if match else None


class _LeverFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.standard_fields: list[tuple[str, bool, bool]] = []  # (label, required, is_file)
        self.card_templates: list[str] = []
        self.custom_question_count = 0
        self.has_comments = False
        self._question_classes: list[str] | None = None
        self._in_label = False
        self._label_parts: list[str] = []
        self._label_required = False

    @override
    def handle_starttag(self, tag: str, attribute_pairs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attribute_pairs)
        classes = (attributes.get("class") or "").split()
        self._note_markup(tag, attributes, classes)
        self._track_label(tag, classes)

    def _note_markup(self, tag: str, attributes: dict[str, str | None], classes: list[str]) -> None:
        if tag == "li" and "custom-question" in classes:
            self.custom_question_count += 1
        if tag == "textarea" and attributes.get("name") == "comments":
            self.has_comments = True
        if tag == "input" and "[baseTemplate]" in (attributes.get("name") or ""):
            self.card_templates.append(attributes.get("value") or "")

    def _track_label(self, tag: str, classes: list[str]) -> None:
        if tag == "li" and "application-question" in classes:
            self._question_classes = classes
        elif tag == "div" and "application-label" in classes and self._question_classes is not None:
            self._in_label = True
            self._label_parts = []
            self._label_required = False
        elif tag == "span" and self._in_label and "required" in classes:
            self._label_required = True

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag != "div" or not self._in_label or self._question_classes is None:
            return
        self._in_label = False
        if "custom-question" not in self._question_classes:
            label = " ".join("".join(self._label_parts).replace(_REQUIRED_MARK, "").split())
            if label:
                self.standard_fields.append(
                    (label, self._label_required, "resume" in self._question_classes)
                )
        self._question_classes = None

    @override
    def handle_data(self, data: str) -> None:
        if self._in_label:
            self._label_parts.append(data)


def parse_lever_form(page: str) -> list[FormQuestion]:
    parser = _LeverFormParser()
    parser.feed(page)
    questions = [
        FormQuestion(
            label=label,
            kind=QuestionKind.FILE if is_file else QuestionKind.TEXT,
            required=required,
        )
        for label, required, is_file in parser.standard_fields
    ]
    questions_from_cards = [
        question for template in parser.card_templates for question in card_questions(template)
    ]
    if len(questions_from_cards) != parser.custom_question_count:
        raise ValueError(
            f"Lever form has {parser.custom_question_count} custom questions in the markup "
            f"but {len(questions_from_cards)} were read from card templates"
        )
    additional = [_ADDITIONAL_INFORMATION] if parser.has_comments else []
    return questions + questions_from_cards + additional


async def fetch_lever_questions(
    company: str, posting_id: str, client: httpx.AsyncClient
) -> list[FormQuestion]:
    response = await client.get(
        APPLY_PAGE.format(company=company, posting_id=posting_id), headers=HEADERS
    )
    if response.status_code != httpx.codes.OK:
        logger.warning(
            "lever apply page for %s/%s unavailable: HTTP %s",
            company,
            posting_id,
            response.status_code,
        )
        return []
    return parse_lever_form(response.text)


class LeverSource:
    name = "lever"

    def match(self, job: Job) -> SourceMatch | None:
        found = posting_from_url(job.url)
        return SourceMatch(self, found) if found else None

    async def questions(self, match: SourceMatch, client: httpx.AsyncClient) -> list[FormQuestion]:
        company, posting_id = match.locator
        return await fetch_lever_questions(company, posting_id, client)

    async def required_fields(
        self,
        match: SourceMatch,  # noqa: ARG002 - QuestionSource's signature; the apply page is read through questions
        client: httpx.AsyncClient,  # noqa: ARG002 - QuestionSource's signature; the apply page is read through questions
    ) -> tuple[str, ...]:
        return ()
