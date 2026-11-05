"""MCP tools for the application sheet and the pipeline: prepare, list by status, update."""

from datetime import datetime
from typing import Any

from mcp.server.mcpserver import Context

from moonlighter._tool_logging import tool_logged
from moonlighter.app_context import AppContext, refreshed_app_context
from moonlighter.application.answers.answer_bank import promote_application
from moonlighter.application.assisted import service as assisted_service
from moonlighter.application.assisted.results import render_sheet_result
from moonlighter.core.db import Application, Job, sync_job_status
from moonlighter.core.metrics import operation_metrics
from moonlighter.startup import StartupWarning, validate_startup

_PIPELINE_STATUSES = (
    "draft",
    "needs_review",
    "submitted",
    "screening",
    "interviews",
    "offer",
    "rejected",
)
_ACCEPTED_STATUSES = {"screening", "interviews", "offer", "rejected", "submitted", "draft"}


@tool_logged
async def prepare_application(job_id: int, *, context: Context[AppContext, Any]) -> str:
    """
    Produce the full set of answers for a job application, for you to paste into
    the form yourself. Reads the questions from the ATS when it publishes its form
    (Greenhouse, Recruitee, Workable, Lever); otherwise asks you to copy the page.
    InHire lists its required fields in that paste request, so you know up front
    what its form will insist on.
    job_id: ID of the job
    """  # noqa: D205, D212, D415 - served verbatim as the MCP tool description
    app_context = refreshed_app_context(context)
    with operation_metrics("prepare_application"):
        return render_sheet_result(
            await assisted_service.prepare_application(
                job_id, app_context.config, app_context.profile
            )
        )


@tool_logged
async def prepare_application_from_paste(
    job_id: int, page_text: str, *, context: Context[AppContext, Any]
) -> str:
    """
    Same as prepare_application, for a page whose questions no API publishes:
    select the whole application page, copy it, and pass the text here. When the
    job's ATS publishes its form, the paste is ignored and the published form is
    used instead.
    job_id: ID of the job
    page_text: everything copied off the application page
    """  # noqa: D205, D212, D415 - served verbatim as the MCP tool description
    app_context = refreshed_app_context(context)
    with operation_metrics("prepare_application_from_paste"):
        return render_sheet_result(
            await assisted_service.prepare_application_from_paste(
                job_id, page_text, app_context.config, profile=app_context.profile
            )
        )


def _warning_lines(warnings: list[StartupWarning]) -> list[str]:
    if not warnings:
        return []
    lines = ["# Setup Warnings\n"]
    for warning in warnings:
        marker = "ERROR" if warning.level == "error" else "WARN"
        lines.append(f"- [{marker}] {warning.message}")
    lines.append("")
    return lines


def _application_line(application: Application) -> str:
    date = application.applied_at.strftime("%d/%m") if application.applied_at else "—"
    next_action = f" → {application.next_action}" if application.next_action else ""
    return (
        f"- #{application.job.id} {application.job.company}/{application.job.title} "
        f"({date}){next_action}"
    )


def _status_section(status: str) -> list[str]:
    applications = list(
        Application.select(Application, Job)
        .join(Job)
        .where(Application.status == status)
        .order_by(Application.updated_at.desc())
    )
    if not applications:
        return []
    lines = [f"## {status.capitalize()} ({len(applications)})"]
    lines.extend(_application_line(application) for application in applications)
    lines.append("")
    return lines


@tool_logged
async def get_pipeline(*, context: Context[AppContext, Any]) -> str:
    """Show full application funnel: counts and list by status."""
    app_context = refreshed_app_context(context)
    lines = _warning_lines(validate_startup(app_context.config, app_context.profile))
    lines.append("# Application Pipeline\n")
    for status in _PIPELINE_STATUSES:
        lines.extend(_status_section(status))
    lines.append(f"**Total applications:** {Application.select().count()}")
    return "\n".join(lines)


def _apply_update(application: Application, status: str, *, notes: str, next_action: str) -> None:
    application.status = status
    application.updated_at = datetime.now()  # noqa: DTZ005 - the database stores naive local time
    if notes:
        existing = application.notes or ""
        today = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005 - the database stores naive local time
        application.notes = f"{existing}\n[{today}] {notes}".strip()
    if next_action:
        application.next_action = next_action


@tool_logged
async def update_status(
    job_id: int,
    status: str,
    notes: str = "",
    *,
    next_action: str = "",
) -> str:
    """
    Update application status manually.
    status: 'screening' | 'interviews' | 'offer' | 'rejected' | 'submitted' | 'draft'
    notes: free text notes appended to history
    next_action: e.g. 'follow up on 2026-06-01'
    """  # noqa: D205, D212, D415 - served verbatim as the MCP tool description
    if status not in _ACCEPTED_STATUSES:
        return f"Invalid status. Accepted values: {', '.join(sorted(_ACCEPTED_STATUSES))}"
    try:
        job = Job.get_by_id(job_id)
        application = Application.get(Application.job == job)
    except Job.DoesNotExist, Application.DoesNotExist:
        return f"Job #{job_id} not found or has no registered application."

    _apply_update(application, status, notes=notes, next_action=next_action)
    application.save()
    sync_job_status(application)
    if status == "submitted":
        promote_application(application.get_form_data(), job_id)

    result = f"✓ Job #{job_id} ({job.company}/{job.title}): status → {status}"
    if next_action:
        result += f"\n  Next action: {next_action}"
    return result
