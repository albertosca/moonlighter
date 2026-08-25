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


def normalize_remote_type(location: str | None) -> str | None:
    """Derive remote_type from a location string — explicit terms only.

    EN and PT-BR vocabularies (live bug iFood #2811, 2026-08-24: "Remoto"
    derived 'onsite'). A bare place name returns None, never 'onsite': the
    old default invented on-site for anything unrecognized, and once the
    regional eligibility filter began cutting onsite/hybrid outside Belo
    Horizonte deterministically, an invented 'onsite' became an invented
    archive. Unknown stays unknown and the evaluator decides, seeing both
    fields."""
    if not location:
        return None
    loc = location.lower()
    if "hybrid" in loc or "híbrido" in loc or "hibrido" in loc:
        return "hybrid"
    if "remote" in loc or "remoto" in loc:
        return "remote"
    if (
        "on-site" in loc
        or "onsite" in loc
        or "presencial" in loc
        or "in office" in loc
        or "in-office" in loc
    ):
        return "onsite"
    return None


class BaseScanner(ABC):
    @abstractmethod
    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        """Fetch raw job listings. Returns deduplicated list of RawJob."""
        ...
