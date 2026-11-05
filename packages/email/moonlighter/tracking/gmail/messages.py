"""Reading Gmail: the recent-messages search and the fields a reply is classified on."""

import logging
from typing import Any

from moonlighter.tracking.gmail.message_body import extract_body

logger = logging.getLogger(__name__)

_MAXIMUM_PAGES = 10  # hard upper bound: 10 pages × 50/page = 500 messages per sync, max


def fetch_recent_messages(
    service: Any, lookback_days: int = 30, maximum_results: int = 50
) -> list[dict[str, Any]]:
    """Recent messages, whether or not they have been read.

    Returns a list of {id, threadId}.

    Read state is deliberately not part of the search: a person reads their mail, and
    a reply that has been read is exactly the reply worth recording. Re-processing is
    prevented by ProcessedEmail, not by the unread flag.

    `in:anywhere` rather than labelIds=[INBOX]: SPAM is a separate label from INBOX,
    so the label filter hid every message Gmail had flagged. ATS confirmations sent to
    a plus-alias land there routinely — one did, for the holepunch application on
    2026-08-04 — and "we received your application" is the single reply least worth
    missing.

    Paginates via nextPageToken up to _MAXIMUM_PAGES pages, so a mailbox with more than
    maximum_results messages inside the lookback window doesn't silently lose the older
    ones: Gmail returns newest-first and the query can't exclude already-processed
    messages, so a single unpaginated page truncates and those older messages age out
    of the window before ever being fetched — with no drain mechanism (the previous
    is:unread design had one: marking a message read removed it from the query; this
    time-window design doesn't). The page bound exists so a huge mailbox can't spin
    forever; hitting it is logged just like hitting maximum_results on a single page.
    """
    query = f"newer_than:{lookback_days}d in:anywhere"
    messages: list[dict[str, Any]] = []
    page_token: str | None = None
    for page in range(1, _MAXIMUM_PAGES + 1):
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=maximum_results,
                pageToken=page_token,
            )
            .execute()
        )
        page_messages = response.get("messages", [])
        messages.extend(page_messages)
        if len(page_messages) == maximum_results:
            logger.warning(
                "fetch_recent_messages: page %d returned the full %d-message cap — "
                "more messages may exist in the %dd lookback window",
                page,
                maximum_results,
                lookback_days,
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    else:
        logger.warning(
            "fetch_recent_messages: hit the %d-page cap (%d messages fetched) — "
            "older messages in the %dd lookback window may still be unfetched",
            _MAXIMUM_PAGES,
            len(messages),
            lookback_days,
        )
    return messages


def parse_message(service: Any, message_id: str) -> dict[str, Any]:
    """Extracts to, from_, subject, body from a Gmail message."""
    raw = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = raw.get("payload", {})
    headers = {header["name"].lower(): header["value"] for header in payload.get("headers", [])}
    return {
        "to": headers.get("to", ""),
        "from_": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "body": extract_body(payload),
    }
