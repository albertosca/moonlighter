from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


class ScannerSessionExpiredError(Exception):
    """Raised by a browser-based scanner (see BaseScanner) when the page it's
    driving redirects to a login/checkpoint wall instead of showing results --
    the operator's session needs re-authentication. The generic dispatcher in
    discovery/service.py catches this by base type, so any scanner (public or a
    privately-registered plugin) can signal it without the dispatcher needing to
    import that scanner's own exception type."""


@dataclass
class RawJob:
    source: str
    company: str
    title: str
    url: str
    location: str | None = None
    remote_type: str | None = None  # 'remote' | 'hybrid' | 'onsite'
    description: str | None = None
    posted_at: datetime | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_source: str | None = None  # 'stated' only (scanner doesn't infer)


@dataclass
class SourceStats:
    """Per-source fetch accounting for one scan run (see _gather_jobs)."""

    companies: int = 0  # 0 means a portal feed, not a per-company board
    jobs: int = 0
    errors: int = 0


ScanStats = dict[str, SourceStats]


_HYBRID_TERMS = ("hybrid", "híbrido", "hibrido")
_REMOTE_TERMS = ("remote", "remoto")
_ONSITE_TERMS = ("on-site", "onsite", "presencial", "in office", "in-office")


def remote_types_mentioned(text: str | None) -> set[str]:
    """Every remote_type kind the text states explicitly (EN and PT-BR)."""
    if not text:
        return set()
    lowered = text.lower()
    mentioned = set()
    for kind, terms in (
        ("hybrid", _HYBRID_TERMS),
        ("remote", _REMOTE_TERMS),
        ("onsite", _ONSITE_TERMS),
    ):
        if any(term in lowered for term in terms):
            mentioned.add(kind)
    return mentioned


def normalize_remote_type(location: str | None) -> str | None:
    """Derive remote_type from a location string — explicit terms only.

    EN and PT-BR vocabularies (live bug iFood #2811, 2026-08-24: "Remoto"
    derived 'onsite'). A bare place name returns None, never 'onsite': the
    old default invented on-site for anything unrecognized, and once the
    regional eligibility filter began cutting onsite/hybrid outside the home
    city deterministically, an invented 'onsite' became an invented
    archive. Unknown stays unknown and the evaluator decides, seeing both
    fields."""
    mentioned = remote_types_mentioned(location)
    for kind in ("hybrid", "remote", "onsite"):
        if kind in mentioned:
            return kind
    return None


_MAXIMUM_LOCATIONS = 8


def join_locations(primary: object, extras: object) -> str | None:
    """One location string for a posting that lists several places.

    Boards like Lever (`allLocations`) and Ashby (`secondaryLocations`) publish
    a primary place plus others; keeping only the primary hid a "Remote" option
    that sat among them (116 Ashby and 7 Lever postings, measured 2026-10-24).
    Primary first, repeats and blanks dropped, capped so the evaluator prompt
    stays small. The text stays literal: no region enum, the evaluator reads it."""
    candidates = [primary, *(extras if isinstance(extras, list) else [])]
    places: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        place = candidate.strip()
        if place and place not in places:
            places.append(place)
    return "; ".join(places[:_MAXIMUM_LOCATIONS]) or None


def remote_type_from_workplace(workplace_type: object) -> str | None:
    """Map a board API's structured workplace field (Lever `workplaceType`:
    onsite/hybrid/remote/unspecified; Ashby: OnSite/Hybrid/Remote) to remote_type.

    Callers use it only when the location TEXT is silent: a live Lever board
    (shieldai) says "Remote" in the location and `onsite` in the field, and an
    API-derived 'onsite' outside the home city is a hard archive."""
    if not isinstance(workplace_type, str):
        return None
    return normalize_remote_type(workplace_type.replace("_", "-"))


class BaseScanner(ABC):
    @abstractmethod
    async def scan(self, company_slugs: list[str], **keyword_arguments: Any) -> list[RawJob]:
        """Fetch raw job listings. Returns deduplicated list of RawJob."""
        ...
