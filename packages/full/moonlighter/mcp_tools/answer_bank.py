"""MCP tools for the shared answer bank: list what would be replayed, forget one answer."""

from typing import Any

from mcp.server.mcpserver import Context

from moonlighter._tool_logging import tool_logged
from moonlighter.app_context import AppContext, refreshed_app_context
from moonlighter.application.answers.bank.eligibility import normalize_question
from moonlighter.application.answers.bank.store import (
    forget,
    list_entries,
    render_answer_bank,
)
from moonlighter.core.config.defaults import DEFAULTS


@tool_logged
async def list_answer_bank(*, context: Context[AppContext, Any]) -> str:
    """
    Every banked screening answer, most recently used first. Entries older than
    answer_bank_max_age_days are marked expired: kept, but no longer replayed
    on a sheet until a new submission refreshes them.
    """  # noqa: D205, D212 - served verbatim as the MCP tool description
    app_context = refreshed_app_context(context)
    max_age = app_context.config.get(
        "answer_bank_max_age_days", DEFAULTS["answer_bank_max_age_days"]
    )
    return render_answer_bank(list_entries(), max_age)


@tool_logged
async def forget_answer(question: str) -> str:
    """
    Delete one banked answer by its question text (matched the way the bank
    keys it: lowercase, collapsed whitespace, no trailing punctuation). Use it
    when list_answer_bank shows an answer that is wrong or stale; the next
    application that asks the question goes to the LLM again.
    """  # noqa: D205, D212 - served verbatim as the MCP tool description
    normalized = normalize_question(question)
    if forget(question):
        return f"Forgot the banked answer for '{normalized}'."
    return f"No banked answer matches '{normalized}'."
