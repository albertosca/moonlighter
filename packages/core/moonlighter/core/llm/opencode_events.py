"""Reading `opencode run --format json`: the answer, the session id, errors and tool calls."""

import json
from dataclasses import dataclass
from typing import Any

from moonlighter.core.llm.spend_limit import is_spend_limit


@dataclass(frozen=True)
class RunOutput:
    """What one run printed: joined text, its session, its errors and the tools it called."""

    answer: str
    session_id: str | None
    error: str | None
    tools: tuple[str, ...]


def _events(stdout: bytes) -> list[dict[str, Any]]:
    """Each line that is a JSON object; anything else opencode prints is skipped."""
    events = []
    for line in stdout.decode(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _parts(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    """The `part` objects of the events of one type."""
    return [
        event["part"]
        for event in events
        if event.get("type") == event_type and isinstance(event.get("part"), dict)
    ]


def _error_message(error: object) -> str:
    """The error's message, prefixed `usage limit: ` when it reads as a quota."""
    details: dict[str, Any] = error if isinstance(error, dict) else {}
    message = str(details.get("message") or details.get("type") or error)
    limited = (
        details.get("type") == "provider.free-limit"
        or details.get("status") == 429  # noqa: PLR2004 - HTTP 429 Too Many Requests
        or is_spend_limit(RuntimeError(message))
    )
    return f"usage limit: {message}" if limited else message


def parse_events(stdout: bytes) -> RunOutput:
    """What one run printed."""
    events = _events(stdout)
    errors = [
        _error_message(event.get("error")) for event in events if event.get("type") == "error"
    ]
    session_ids = [
        event["sessionID"] for event in events if isinstance(event.get("sessionID"), str)
    ]
    return RunOutput(
        answer="".join(str(part.get("text", "")) for part in _parts(events, "text")),
        session_id=session_ids[0] if session_ids else None,
        error="; ".join(errors) or None,
        tools=tuple(str(part.get("tool")) for part in _parts(events, "tool_use")),
    )
