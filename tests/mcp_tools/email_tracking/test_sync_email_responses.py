"""What sync_email_responses reports for the replies it found."""

from unittest.mock import AsyncMock, patch

from moonlighter.core.db import init_db
from moonlighter.mcp_tools.email_tracking import sync_email_responses

from tests._context import make_test_context


async def test_sync_email_responses_returns_summary(temporary_database):
    """sync_email_responses should call sync_responses and return a readable summary."""
    init_db()

    fake_updates = [
        {
            "company": "Anthropic",
            "title": "Senior Engineer",
            "type": "interview",
            "stage": "technical_interview",
            "match_type": "ref",
        },
        {
            "company": "Stripe",
            "title": "Backend Eng",
            "type": "rejection",
            "stage": None,
            "match_type": "fuzzy",
        },
    ]
    test_config = {
        "email": {
            "address": "candidaturas@gmail.com",
            "credentials_path": "~/.moonlighter/gmail-client.json",
            "token_path": "~/.moonlighter/gmail-token.json",
            "processed_label": "moonlighter/processed",
            "interview_stages": [],
        },
        "llm_model": "claude-sonnet-4-6",
    }

    with patch(
        "moonlighter.mcp_tools.email_tracking.sync_responses",
        new=AsyncMock(return_value=fake_updates),
    ):
        result = await sync_email_responses(context=make_test_context(config=test_config))

    assert "Anthropic" in result
    assert "Stripe" in result
    assert "2" in result or len(result) > 10


async def test_sync_email_responses_empty_inbox(temporary_database):
    """sync_email_responses with an empty inbox should return an appropriate message."""
    init_db()

    test_config = {
        "email": {
            "address": "candidaturas@gmail.com",
            "credentials_path": "~/.moonlighter/gmail-client.json",
            "token_path": "~/.moonlighter/gmail-token.json",
            "processed_label": "moonlighter/processed",
            "interview_stages": [],
        },
        "llm_model": "claude-sonnet-4-6",
    }

    with patch(
        "moonlighter.mcp_tools.email_tracking.sync_responses", new=AsyncMock(return_value=[])
    ):
        result = await sync_email_responses(context=make_test_context(config=test_config))

    assert "no new" in result.lower() or "0" in result


async def test_sync_email_responses_flags_fuzzy_match_as_suggestion(temporary_database):
    """S-06: the sync_email_responses report must tell the human a fuzzy match
    was NOT applied and needs manual update_status confirmation."""
    init_db()

    with patch(
        "moonlighter.mcp_tools.email_tracking.sync_responses",
        new=AsyncMock(
            return_value=[
                {
                    "company": "Stripe",
                    "title": "Backend Engineer",
                    "type": "interview",
                    "stage": "technical_interview",
                    "match_type": "fuzzy",
                    "summary": "x",
                    "suggested_job_id": 42,
                    "needs_confirmation": True,
                }
            ]
        ),
    ):
        result = await sync_email_responses(context=make_test_context())

    assert "update_status" in result
    assert "42" in result
    assert "⚠️" in result
