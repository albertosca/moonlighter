"""Rejection-aware queue ordering, computed at read time.

Provenance: 2026-08-24 (Alberto) — Holepunch #3197 was offered without anyone
knowing the same company rejected #3200 eight days earlier; the information
was in the DB and nothing surfaced it.

The persisted score is never touched: the penalty is derived on read, so it
decays as rejections age without re-scoring anything, reorders the listing
toward the end, and never hides a job. Incremental by design — two recent
rejections weigh more than one.
"""

import datetime

from moonlighter.core.db import Application, Job

REJECTION_WINDOW_DAYS = 90


def company_rejection_ages(now: datetime.datetime | None = None) -> dict[str, list[float]]:
    """Ages (in days) of every rejected Application, keyed by lowercased
    company — 'Holepunch' and 'holepunch' are the same employer."""
    now = now or datetime.datetime.now()
    ages: dict[str, list[float]] = {}
    query = Application.select(Application, Job).join(Job).where(Application.status == "rejected")
    for app in query:
        when = app.updated_at or now
        ages.setdefault(app.job.company.lower(), []).append((now - when).total_seconds() / 86400)
    return ages


def rejection_penalty(ages: list[float]) -> float:
    """Score points to subtract at sort time: each rejection inside the window
    contributes linearly from 1.0 (today) down to 0.0 (window edge)."""
    return sum(max(0.0, 1.0 - age / REJECTION_WINDOW_DAYS) for age in ages)


def rejection_badge(ages: list[float]) -> str | None:
    """Human-facing warning for the listing, or None without recent history."""
    recent = sorted(age for age in ages if age <= REJECTION_WINDOW_DAYS)
    if not recent:
        return None
    return f"⚠ rejected {len(recent)}x, last {round(recent[0])}d ago"
