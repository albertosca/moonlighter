"""Register an application made outside the tool, from `moonlighter-email register` or the MCP.

Marks the job as applied and mints its +ref tracking alias without the apply
slice installed; only core models are touched. Additive only: a row that
already exists is never overwritten — a draft is promoted, a null date is
filled when one was given, a note is appended.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from moonlighter.core.db import Application, Job
from moonlighter.core.email_alias import build_email_alias, new_email_ref
from moonlighter.core.job_status import sync_job_status
from moonlighter.core.notes import append_dated_note

ACCEPTED_STATUSES: tuple[str, ...] = (
    "submitted",
    "screening",
    "interviews",
    "offer",
    "rejected",
    "no_response",
)


class RegisterKind(StrEnum):
    REGISTERED = "registered"
    JOB_NOT_FOUND = "job_not_found"
    INVALID_STATUS = "invalid_status"


@dataclass(frozen=True)
class RegisterRequest:
    status: str = "submitted"
    applied_at: datetime | None = None
    notes: str = ""
    # None leaves the flag as it is; True/False sets it.
    reply_mailbox_unswept: bool | None = None


@dataclass(frozen=True)
class RegisterResult:
    kind: RegisterKind
    job_id: int
    application_id: int | None = None
    status: str | None = None
    email_ref: str | None = None
    alias: str | None = None
    error: str | None = None
    created: bool = False


def register_application(
    job_id: int, config: dict[str, Any], request: RegisterRequest | None = None
) -> RegisterResult:
    request = request or RegisterRequest()
    if request.status not in ACCEPTED_STATUSES:
        return RegisterResult(
            RegisterKind.INVALID_STATUS,
            job_id,
            error=f"Invalid status {request.status!r}. Accepted: {', '.join(ACCEPTED_STATUSES)}.",
        )
    job = Job.get_or_none(Job.id == job_id)
    if job is None:
        return RegisterResult(RegisterKind.JOB_NOT_FOUND, job_id, error=f"Job {job_id} not found.")
    now = datetime.now()  # noqa: DTZ005 - the database stores naive local time
    application, created = Application.get_or_create(
        job=job, defaults={"status": request.status, "applied_at": request.applied_at or now}
    )
    _merge(application, request, now=now)
    application.updated_at = now
    application.save()
    sync_job_status(application)
    return _registered(application, config, job_id=job_id, created=created)


def _merge(application: Application, request: RegisterRequest, *, now: datetime) -> None:
    """Additive only: a draft is promoted, a null date filled when one was given, a note appended."""
    if application.status == "draft":
        application.status = request.status
        application.applied_at = request.applied_at or now
    elif application.applied_at is None and request.applied_at is not None:
        application.applied_at = request.applied_at
    if request.notes:
        application.notes = append_dated_note(application.notes, request.notes, now.date())
    if request.reply_mailbox_unswept is not None:
        application.reply_mailbox_unswept = request.reply_mailbox_unswept
    if not application.email_ref:
        application.email_ref = new_email_ref()


def _registered(
    application: Application, config: dict[str, Any], *, job_id: int, created: bool
) -> RegisterResult:
    address = (config.get("email") or {}).get("address")
    # _merge minted the ref when it was missing, so str() only narrows the type.
    alias = build_email_alias(str(address), str(application.email_ref)) if address else None
    return RegisterResult(
        RegisterKind.REGISTERED,
        job_id,
        application_id=application.id,
        status=application.status,
        email_ref=application.email_ref,
        alias=alias,
        created=created,
    )


def register_to_dict(result: RegisterResult) -> dict[str, Any]:
    return {**asdict(result), "kind": result.kind.value}
