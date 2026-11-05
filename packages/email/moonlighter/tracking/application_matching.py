"""Which application an email reply belongs to: by its plus-alias ref, or by company and title."""

import re
from typing import Any

from peewee import fn

from moonlighter.core.db import Application, Job

_ACTIVE_STATUSES = ["submitted", "screening", "interviews", "offer"]


def extract_ref(to_field: str, base_address: str) -> str | None:
    """Extracts the ref from a Gmail (+ref) alias in the To field.

    "you+x7k2mp@gmail.com" → "x7k2mp"
    None if there's no alias or it doesn't match base_address.
    """
    if not to_field:
        return None

    local, _, domain = base_address.partition("@")
    for part in re.split(r",\s*", to_field):  # the To field can have multiple addresses
        match = re.search(r"<([^>]+)>", part)  # "Name <email>" → "email"
        address = match.group(1).strip() if match else part.strip()

        address_local, _, address_domain = address.partition("@")
        if address_domain.lower() != domain.lower() or "+" not in address_local:
            continue
        base_local, _, reference = address_local.partition("+")
        if base_local.lower() == local.lower() and reference:
            return reference

    return None


def resolve_application(reference: str | None, classification: dict[str, Any]) -> tuple[Any, str]:
    """Finds the matching Application, by ref (exact) or company+title (fuzzy).

    Returns (Application | None, 'ref' | 'fuzzy' | 'uncertain').
    """
    if reference:
        application = _match_by_ref(reference)
        if application is not None:
            return application, "ref"

    application = _match_by_company_title(
        classification.get("company"), classification.get("job_title")
    )
    if application is not None:
        return application, "fuzzy"
    return None, "uncertain"


def _match_by_ref(reference: str) -> Any:
    # Refs minted before 2026-08-06 are mixed case, and providers lowercase the local
    # part on the way back, so both sides are folded rather than the column migrated.
    return Application.get_or_none(fn.LOWER(Application.email_ref) == reference.lower())


def _match_by_company_title(company: str | None, job_title: str | None) -> Any:
    """Fuzzy match among active applications.

    Returns the single Application, or None when there's no candidate or it's
    ambiguous (>1 — can't decide).
    """
    if not (company or job_title):
        return None

    query = (
        Application.select(Application, Job)
        .join(Job)
        .where(Application.status.in_(_ACTIVE_STATUSES))
    )
    if company:
        query = query.where(Job.company ** f"%{company}%")
    if job_title:
        query = query.where(Job.title ** f"%{job_title}%")

    results = list(query)
    return results[0] if len(results) == 1 else None
