"""The contract every form-question source implements, and the guard around it.

A source answers two questions about one job: does it know this job's form
(`match`, no network), and what does the form ask (`questions`). `[]` from
`questions` means "this source does not have the form" and sends the person to
the paste path — never "the form has zero questions". `required_fields` exists
for sources that publish only which built-in fields are required (InHire).
"""

import logging
import re
from dataclasses import dataclass
from typing import Protocol

import httpx
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.core.db import Job

logger = logging.getLogger(__name__)

# A job id in a URL path: a real 8-4-4-4-12 UUID, not merely 36 id-ish
# characters, and not the prefix of a longer id.
UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f-])"

# A Yes/No QUESTION has one shape whatever the source (2026-09-29): a
# single_select with the page's two answers, so the answer is pinned to an
# offered option and the sheet shows the one not chosen. A statement to tick
# (consent) stays boolean. Every source builds the question through
# `yes_no_question`; the paste path also uses `yes_no_for` as its backstop.
YES_NO = ("Yes", "No")

# The answers follow the question's language (2026-10-05: a Portuguese question
# got English Yes/No). Words that mark a language in a short form question; the
# most hits wins, and a tie or no hit at all stays English.
_YES_NO_BY_LANGUAGE: dict[str, tuple[str, str]] = {
    "en": YES_NO,
    "pt": ("Sim", "Não"),
    "es": ("Sí", "No"),
    "fr": ("Oui", "Non"),
    "de": ("Ja", "Nein"),
}
_LANGUAGE_MARKERS: dict[str, frozenset[str]] = {
    "en": frozenset({"you", "your", "are", "do", "have", "will", "can", "work", "authorized"}),
    "pt": frozenset(
        {
            "você",
            "voce",
            "possui",
            "tem",
            "aceita",
            "deseja",
            "concorda",
            "está",
            "já",
            "sua",
            "seu",
            "em",
            "trabalhar",
            "disponibilidade",
            "não",
            "pode",
            "é",
        }
    ),
    "es": frozenset(
        {
            "usted",
            "tiene",
            "tienes",
            "puede",
            "acepta",
            "permiso",
            "trabajo",
            "trabajar",
            "en",
            "su",
            "es",
        }
    ),
    "fr": frozenset({"vous", "êtes", "avez", "votre", "est", "disponible", "acceptez"}),
    "de": frozenset({"sie", "haben", "sind", "können", "ihre", "ihr", "eine", "einen", "besitzen"}),
}


def yes_no_for(label: str) -> tuple[str, str]:
    words = re.findall(r"[^\W\d_]+", label.lower())
    scores = {
        language: sum(word in markers for word in words)
        for language, markers in _LANGUAGE_MARKERS.items()
    }
    if label.lstrip().startswith("¿"):
        scores["es"] += 2
    best = max(scores.values())
    leaders = [language for language, score in scores.items() if score == best]
    if best == 0 or len(leaders) > 1:
        return YES_NO
    return _YES_NO_BY_LANGUAGE[leaders[0]]


def is_question(label: str) -> bool:
    """The rule for a `boolean` whose widget was never observed: a label ending
    in "?" asks something; anything else is a statement to tick."""
    return label.rstrip().endswith("?")


def yes_no_question(label: str, required: bool, options: tuple[str, ...] = ()) -> FormQuestion:
    """A Yes/No question as a single_select: the source's own option labels when
    its payload carries them, else yes and no in the question's language."""
    return FormQuestion(
        label=label,
        kind=QuestionKind.SINGLE_SELECT,
        required=required,
        options=options or yes_no_for(label),
    )


@dataclass(frozen=True)
class SourceMatch:
    source: QuestionSource
    locator: tuple[str, ...]


class QuestionSource(Protocol):
    name: str

    def match(self, job: Job) -> SourceMatch | None: ...

    async def questions(
        self, match: SourceMatch, client: httpx.AsyncClient
    ) -> list[FormQuestion]: ...

    async def required_fields(
        self, match: SourceMatch, client: httpx.AsyncClient
    ) -> tuple[str, ...]: ...


async def questions_or_empty(match: SourceMatch, client: httpx.AsyncClient) -> list[FormQuestion]:
    """A source that cannot be reached or read has no form: the caller asks for a paste.

    Any exception, not just transport and decoding errors: a payload whose shape the
    parser never anticipated raises TypeError/AttributeError, and that must reach the
    person as the paste hint, never as a crashed `prepare_application`."""
    try:
        return await match.source.questions(match, client)
    except Exception as error:
        logger.warning("%s questions unavailable: %s", match.source.name, error, exc_info=True)
        return []


async def required_fields_or_empty(
    match: SourceMatch, client: httpx.AsyncClient
) -> tuple[str, ...]:
    try:
        return await match.source.required_fields(match, client)
    except Exception as error:
        logger.warning(
            "%s required fields unavailable: %s", match.source.name, error, exc_info=True
        )
        return ()
