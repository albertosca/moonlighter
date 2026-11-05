"""Where a reply moves its application in the funnel: forward only, with a dated note."""

from datetime import date, datetime
from typing import Any

from moonlighter.core.job_status import sync_job_status

# Canonical funnel progression order — the status only ever moves forward, never back.
_STATUS_ORDER = ["draft", "submitted", "screening", "interviews", "offer", "rejected"]

_TYPE_TO_STATUS = {
    "screening": "screening",
    "interview": "interviews",
    "offer": "offer",
    "rejection": "rejected",
    # acknowledgement, info_request and unrelated → keeps the current status
}


def advance_application(
    application: Any, classification: dict[str, Any], match_type: str, *, stages: list[str]
) -> bool:
    """Advances the Application through the funnel (forward only) and notes the event.

    Returns whether the status actually moved forward.

    current_stage is only written if the value is in the list of known stages
    (which already includes any new_stage legitimately registered by
    register_new_stage BEFORE this call) — a stage outside that list is
    hallucination/injection and is silently discarded (S-05).
    """
    new_status = _TYPE_TO_STATUS.get(classification["type"])
    advanced = new_status is not None and _status_rank(new_status) > _status_rank(
        application.status
    )
    if advanced:
        application.status = new_status
    stage = classification.get("stage")
    if stage and stage in stages:
        application.current_stage = stage

    today = date.today().strftime("%Y-%m-%d")  # noqa: DTZ011 - the note is stamped with the local calendar day
    summary = classification.get("summary", "")
    note = f"[{today}] {classification['type']}: {summary} (match: {match_type})"
    application.notes = f"{application.notes}\n{note}" if application.notes else note

    application.updated_at = datetime.now()  # noqa: DTZ005 - the database stores naive local time
    application.save()
    sync_job_status(application)
    return advanced


def _status_rank(status: str) -> int:
    try:
        return _STATUS_ORDER.index(status)
    except ValueError:
        return -1
