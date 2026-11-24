"""Presume dead an application with no sign of life: submitted → no_response after N silent days.

A no-response is not a rejection (Alberto, 2026-11-16): it keeps its own status so the
reply-rate analysis does not mix the two. The rule only trusts a recent complete email
sync, and never touches a row whose replies may land in a mailbox the sync does not read.
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

from moonlighter.core.config.model import Config
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
    unswept: list[dict[str, Any]] = field(default_factory=list)
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


def _mark(application: Application, days: int, now: datetime) -> bool:
    """Mark it, unless the row moved since it was read (an email sync running alongside)."""
    notes = append_dated_note(
        application.notes, f"no_response: no sign of life for {days} days", now.date()
    )
    changed = (
        Application.update(status="no_response", notes=notes, updated_at=now)
        .where(
            Application.id == application.id,
            Application.status == application.status,
            Application.updated_at == application.updated_at,
        )
        .execute()
    )
    if not changed:
        return False
    application.status, application.notes, application.updated_at = "no_response", notes, now
    sync_job_status(application)
    return True


def _swept_since(runs: list[EmailSyncRun]) -> datetime:
    """The start of the unbroken stretch the sweeps read, walking back from the newest.

    `runs` is newest first; a run that finished before the stretch begins leaves a gap,
    and nothing older than the gap counts.
    """
    covered_from: datetime = runs[0].window_start
    for run in runs[1:]:
        if run.finished_at < covered_from:
            break
        covered_from = min(covered_from, run.window_start)
    return covered_from


@dataclass(frozen=True)
class _Sweep:
    swept_since: datetime  # replies before this moment were never read
    now: datetime


def _classify(
    application: Application, days: int, *, result: UnansweredResult, sweep: _Sweep
) -> None:
    if application.status in _LATER_STAGES:
        result.to_review.append({**_summary(application, days), "status": application.status})
    elif application.reply_mailbox_unswept:
        result.held.append(_summary(application, days))
    elif _last_signal(application, sweep.now) < sweep.swept_since:
        result.unswept.append(_summary(application, days))
    elif _mark(application, days, sweep.now):
        result.marked.append(_summary(application, days))


def mark_unanswered_applications(config: Config, now: datetime) -> UnansweredResult:
    """Mark the silent submitted applications, list the silent later stages, hold the flagged."""
    runs = list(EmailSyncRun.select().order_by(EmailSyncRun.finished_at.desc()))
    newest = runs[0] if runs else None
    last_sync = newest.finished_at.isoformat() if newest is not None else None
    after_days = config["no_response_after_days"]
    oldest_trusted_sync_days = config["email_sync_max_age_days"]
    if newest is None or (now - newest.finished_at).days >= oldest_trusted_sync_days:
        return UnansweredResult(ran=False, last_sync=last_sync, after_days=after_days)
    result = UnansweredResult(ran=True, last_sync=last_sync, after_days=after_days)
    sweep = _Sweep(swept_since=_swept_since(runs), now=now)
    candidates = Application.select().where(Application.status.in_(("submitted", *_LATER_STAGES)))
    for application in candidates:
        days = (now.date() - _last_signal(application, now).date()).days
        if days >= after_days:
            _classify(application, days, result=result, sweep=sweep)
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


def _unswept_block(result: UnansweredResult) -> str:
    lines = [
        f"  #{entry['job_id']} {entry['company']}/{entry['title']} ({entry['days']} days)"
        for entry in result.unswept
    ]
    return "\n".join(
        [
            (
                f"{len(result.unswept)} application(s) waiting for an email sync that reaches "
                "back to their last sign of life:"
            ),
            *lines,
            "Raise email.lookback_days in the config to cover them, then run sync_email_responses.",
        ]
    )


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
            (result.unswept, _unswept_block),
        )
        if entries
    ]
    return "\n\n".join(blocks)
