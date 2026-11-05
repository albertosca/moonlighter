"""The readable body of a Gmail message payload, plain text preferred over HTML."""

import base64
from typing import Any


def extract_body(payload: dict[str, Any]) -> str:
    """Extracts the message body, preferring text/plain over text/html."""
    mime = payload.get("mimeType", "")
    if mime in ("text/plain", "text/html"):
        return _decode_data(payload.get("body", {}).get("data", ""))
    if mime.startswith("multipart/"):
        return _extract_multipart(payload.get("parts", []))
    return ""


def _extract_multipart(parts: list[dict[str, Any]]) -> str:
    """Looks for the body in a multipart message.

    text/plain first, then text/html, and finally recurses into nested parts
    (multipart within multipart).
    """
    for preferred in ("text/plain", "text/html"):
        data = _direct_data(parts, preferred)
        if data:
            return _decode_data(data)
    for part in parts:
        body = extract_body(part)
        if body:
            return body
    return ""


def _direct_data(parts: list[dict[str, Any]], mime_type: str) -> str:
    """The encoded data of the first direct part of this type that carries any."""
    for part in parts:
        if part.get("mimeType") == mime_type:
            data: str = part.get("body", {}).get("data", "")
            if data:
                return data
    return ""


def _decode_data(data: str) -> str:
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - a malformed body part decodes to empty instead of aborting the parse
        return ""
