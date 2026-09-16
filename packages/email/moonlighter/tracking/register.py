"""Register an application by hand: the bridge that lets `moonlighter-email
register` mark a job as applied — and mint its +ref tracking alias — without
the apply slice installed. Only core models are touched.
"""

import datetime
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from moonlighter.core.db import Application, Job, sync_job_status
from moonlighter.core.email_alias import build_email_alias, new_email_ref


class RegisterKind(StrEnum):
    REGISTERED = "registered"
    JOB_NOT_FOUND = "job_not_found"


@dataclass(frozen=True)
class RegisterResult:
    kind: RegisterKind
    job_id: int
    application_id: int | None = None
    status: str | None = None
    email_ref: str | None = None
    alias: str | None = None
    error: str | None = None


def register_application(job_id: int, config: dict[str, Any]) -> RegisterResult:
    job = Job.get_or_none(Job.id == job_id)
    if job is None:
        return RegisterResult(RegisterKind.JOB_NOT_FOUND, job_id, error=f"Job {job_id} not found.")
    now = datetime.datetime.now()
    application, _ = Application.get_or_create(
        job=job, defaults={"status": "submitted", "applied_at": now}
    )
    if application.status == "draft":
        application.status = "submitted"
        application.applied_at = now
    if not application.email_ref:
        application.email_ref = new_email_ref()
    application.updated_at = now
    application.save()
    sync_job_status(application)
    address = (config.get("email") or {}).get("address")
    alias = build_email_alias(str(address), application.email_ref) if address else None
    return RegisterResult(
        RegisterKind.REGISTERED,
        job_id,
        application_id=application.id,
        status=application.status,
        email_ref=application.email_ref,
        alias=alias,
    )


def register_to_dict(result: RegisterResult) -> dict[str, Any]:
    return {**asdict(result), "kind": result.kind.value}
