"""MCP tools for reply tracking: connect Gmail, then sync replies into the pipeline."""

from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Context

from moonlighter._tool_logging import tool_logged
from moonlighter.app_context import AppContext, refreshed_app_context
from moonlighter.application.answers.bank.store import promote_application
from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.config.paths import resolve_under_home
from moonlighter.core.db import Application
from moonlighter.core.metrics import operation_metrics
from moonlighter.tracking.email_monitor import sync_responses
from moonlighter.tracking.gmail_client import GmailAuthError, run_gmail_oauth, setup_gmail_service


@tool_logged
async def setup_email(*, context: Context[AppContext, Any]) -> str:
    """
    Configure Gmail authentication for the account that receives application replies.
    Run only once. Opens the browser to authorize access.
    Requires the OAuth client file at email.credentials_path
    (default MOONLIGHTER_HOME/gmail-client.json) and writes the token to
    email.token_path — overwriting whatever file that path names.
    """  # noqa: D205, D212 - served verbatim as the MCP tool description
    app_context = refreshed_app_context(context)
    config = app_context.config
    email_config = config.get("email", {})

    # Checked before resolving: Path("").expanduser() is ".", a directory that
    # always exists, so resolving an unconfigured path first would trade this
    # clear message for a confusing "Is a directory" failure further down.
    credentials_path_raw = email_config.get("credentials_path", "")
    if not credentials_path_raw:
        return (
            "⚠️  email.credentials_path is not configured.\n"
            "Download client_secret.json from the Google Cloud Console, save it under "
            "MOONLIGHTER_HOME (or point credentials_path at your own location), and run "
            "setup_email() again."
        )
    credentials_path = str(resolve_under_home(credentials_path_raw))
    token_path = str(
        resolve_under_home(email_config.get("token_path") or DEFAULTS["email"]["token_path"])
    )

    if not Path(credentials_path).exists():  # noqa: ASYNC240 - one stat right before run_gmail_oauth, which blocks on the user's browser anyway
        return (
            f"⚠️  Credentials file not found: {credentials_path}\n"
            "Download client_secret.json from the Google Cloud Console and save it there."
        )

    try:
        run_gmail_oauth(credentials_path, token_path, config)
        setup_gmail_service(config)
    except GmailAuthError as error:
        return f"⚠️  Gmail authentication error: {error}"
    except Exception as error:  # noqa: BLE001 - an unexpected failure gets setup_email's own message, which its test pins; tool_logged's generic line would not say that the Gmail setup failed
        return f"⚠️  Unexpected error configuring Gmail: {error}"
    else:
        return "✓ Gmail authentication configured successfully."


def _promote_advanced_applications(updates: list[dict[str, Any]]) -> None:
    """Promotes the answers of every application an email reply moved forward.

    update_status(..., "submitted") is the operator-driven promotion trigger;
    this is the email-driven one. Without it, a job whose status only ever
    advances through an incoming reply never reached the shared bank — the
    operator has no reason to also mark it "submitted" once the company has
    already replied. Promotion lives in the server's tool layer rather than in
    the email package because moonlighter-email depends on core alone and may
    not import the answer bank; this layer is the one that has both.
    """
    for update in updates:
        if update.get("status_advanced"):
            job_id = update["job_id"]
            application = Application.get(Application.job == job_id)
            promote_application(application.get_form_data(), job_id)


def _update_line(update: dict[str, Any]) -> str:
    company = update.get("company") or "?"
    title = update.get("title") or "?"
    message_type = update.get("type", "?")
    stage = update.get("stage") or ""
    match_type = update.get("match_type", "")
    stage_text = f" → {stage}" if stage else ""
    line = f"- **{company}** / {title}: `{message_type}`{stage_text} (match: {match_type})"
    if update.get("needs_confirmation"):
        line += (
            f" — ⚠️ suggestion not applied; confirm with "
            f"update_status(job_id={update['suggested_job_id']}, status=...)"
        )
    return line


@tool_logged
async def sync_email_responses(*, context: Context[AppContext, Any]) -> str:
    """
    Read recent emails in the configured Gmail account, whether read or unread,
    classify them with the LLM, and update the applications database.
    Returns a summary of the updates made.
    """  # noqa: D205, D212 - served verbatim as the MCP tool description
    app_context = refreshed_app_context(context)
    with operation_metrics("sync_email_responses"):
        updates = await sync_responses(app_context.config, app_context.llm_caller)

        if not updates:
            return "No new emails found."

        _promote_advanced_applications(updates)

        lines = [f"# Email sync — {len(updates)} update(s)\n"]
        lines.extend(_update_line(update) for update in updates)
        return "\n".join(lines)
