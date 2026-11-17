"""Presume dead an application with no sign of life: submitted → no_response after N silent days.

A no-response is not a rejection (Alberto, 2026-11-16): it keeps its own status so the
reply-rate analysis does not mix the two. The rule only trusts a recent complete email
sync, and never touches a row whose replies may land in a mailbox the sync does not read.
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.db import Application, EmailSyncRun, Job
from moonlighter.core.job_status import sync_job_status
from moonlighter.core.notes import append_dated_note, latest_note_date

_LATER_STAGES = ("screening", "interviews", "offer")


@dataclass
class UnansweredResult:
    ran: bool
    last_sync: str | None  # ISO-8601, None when no complete sync ever ran
    marked: list[dict[str, Any]] = field(default_factory=list)
    to_review: list[dict[str, Any]] = field(default_factory=list)
    held: list[dict[str, Any]] = field(default_factory=list)
    after_days: int = 0  # the configured silence, named in the report


def _last_signal(application: Application, now: datetime) -> datetime:
    """The latest of updated_at and the newest dated note; a note dated after today is a typo."""
    signal: datetime = application.updated_at
    noted = latest_note_date(application.notes)
    if noted is not None and noted <= now.date():
        signal = max(signal, datetime.combine(noted, time()))
    return min(signal, now)


def _summary(application: Application, days: int) -> dict[str, Any]:
    job: Job = application.job
    return {"job_id": job.id, "company": job.company, "title": job.title, "days": days}


def _mark(application: Application, days: int, now: datetime) -> None:
    application.status = "no_response"
    application.notes = append_dated_note(
        application.notes, f"no_response: no sign of life for {days} days", now.date()
    )
    application.updated_at = now
    application.save()
    sync_job_status(application)


def _classify(
    application: Application, days: int, *, result: UnansweredResult, now: datetime
) -> None:
    if application.status in _LATER_STAGES:
        result.to_review.append({**_summary(application, days), "status": application.status})
    elif application.reply_mailbox_unswept:
        result.held.append(_summary(application, days))
    else:
        _mark(application, days, now)
        result.marked.append(_summary(application, days))


def mark_unanswered_applications(config: dict[str, Any], now: datetime) -> UnansweredResult:
    """Mark the silent submitted applications, list the silent later stages, hold the flagged."""
    newest = EmailSyncRun.select().order_by(EmailSyncRun.finished_at.desc()).first()
    last_sync = newest.finished_at.isoformat() if newest is not None else None
    after_days = int(config.get("no_response_after_days", DEFAULTS["no_response_after_days"]))
    oldest_trusted_sync_days = int(
        config.get("email_sync_max_age_days", DEFAULTS["email_sync_max_age_days"])
    )
    if newest is None or (now - newest.finished_at).days >= oldest_trusted_sync_days:
        return UnansweredResult(ran=False, last_sync=last_sync, after_days=after_days)
    result = UnansweredResult(ran=True, last_sync=last_sync, after_days=after_days)
    candidates = Application.select().where(Application.status.in_(("submitted", *_LATER_STAGES)))
    for application in candidates:
        days = (now.date() - _last_signal(application, now).date()).days
        if days >= after_days:
            _classify(application, days, result=result, now=now)
    return result


def _not_run_sentence(last_sync: str | None) -> str:
    if last_sync is None:
        return (
            "No-response rule did not run: there is no complete email sync yet. "
            "Run sync_email_responses first."
        )
    return (
        f"No-response rule did not run: the last complete email sync was {last_sync}, "
        "older than email_sync_max_age_days. Run sync_email_responses first."
    )


def _marked_block(result: UnansweredResult) -> str:
    lines = [
        f"  #{entry['job_id']} {entry['company']}/{entry['title']} ({entry['days']} days)"
        for entry in result.marked
    ]
    header = (
        f"{len(result.marked)} application(s) marked no_response "
        f"(no sign of life for {result.after_days}+ days):"
    )
    return "\n".join([header, *lines])


def _review_block(result: UnansweredResult) -> str:
    lines = [
        f"  #{entry['job_id']} {entry['company']}/{entry['title']} — {entry['status']}, "
        f"{entry['days']} days without news: decide by hand"
        for entry in result.to_review
    ]
    return "\n".join(
        [f"{len(result.to_review)} application(s) past the age in a later stage:", *lines]
    )


def _held_block(result: UnansweredResult) -> str:
    lines = [
        f"  #{entry['job_id']} {entry['company']}/{entry['title']} ({entry['days']} days) — "
        "held: replies may be in a mailbox the sync does not read"
        for entry in result.held
    ]
    return "\n".join([f"{len(result.held)} application(s) left alone:", *lines])


def format_unanswered_result(result: UnansweredResult) -> str:
    """The report section: empty when the rule ran and found nothing."""
    if not result.ran:
        return _not_run_sentence(result.last_sync)
    blocks = [
        render(result)
        for entries, render in (
            (result.marked, _marked_block),
            (result.to_review, _review_block),
            (result.held, _held_block),
        )
        if entries
    ]
    return "\n\n".join(blocks)
