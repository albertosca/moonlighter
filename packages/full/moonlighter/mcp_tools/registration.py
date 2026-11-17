"""MCP tool: record an application made outside the tool, in one step."""

from datetime import datetime
from typing import Any

from mcp.server.mcpserver import Context

from moonlighter._tool_logging import tool_logged
from moonlighter.app_context import AppContext, refreshed_app_context
from moonlighter.core.db import Job
from moonlighter.tracking.register import RegisterKind, RegisterRequest, RegisterResult
from moonlighter.tracking.register import register_application as register_service


@tool_logged
async def register_application(  # noqa: PLR0913, PLR0917 - the MCP tool takes these fields as its public arguments
    job_id: int,
    status: str = "submitted",
    applied_at: str = "",
    notes: str = "",
    reply_mailbox_unswept: bool | None = None,  # noqa: FBT001 - an MCP tool argument is passed by name from JSON
    *,
    context: Context[AppContext, Any],
) -> str:
    """
    Record an application you made outside the tool (a form you filled by hand,
    an email you sent, a job below the score threshold you applied to anyway).
    Creates the application if it is missing, moves an archived job out of the
    archive, and never overwrites an application that already exists: it only
    appends the note and fills a missing date.
    job_id: ID of the job (add_job first if it is not in the database)
    status: 'submitted' | 'screening' | 'interviews' | 'offer' | 'rejected' | 'no_response'
    applied_at: YYYY-MM-DD, defaults to today for a new application
    notes: appended to the history with today's date
    reply_mailbox_unswept: true when replies may land in a mailbox the email sync
        does not read; the 45-day no-response rule then leaves it alone
    """  # noqa: D205, D212, D415 - served verbatim as the MCP tool description
    app_context = refreshed_app_context(context)
    try:
        date_given = datetime.fromisoformat(applied_at) if applied_at else None
    except ValueError:
        return f"Invalid applied_at {applied_at!r}: use YYYY-MM-DD."
    request = RegisterRequest(status, date_given, notes, reply_mailbox_unswept)
    return _render(register_service(job_id, app_context.config, request))


def _render(result: RegisterResult) -> str:
    if result.kind is not RegisterKind.REGISTERED:
        return str(result.error)
    job = Job.get_by_id(result.job_id)
    head = f"✓ Job #{job.id} ({job.company}/{job.title}): "
    head += (
        f"application registered, status → {result.status}"
        if result.created
        else f"already registered, status stays {result.status}"
    )
    if result.alias:
        head += f"\n  Reply alias: {result.alias}"
    return head
