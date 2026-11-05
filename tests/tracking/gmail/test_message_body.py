"""Extracting the readable body of a Gmail payload."""

from moonlighter.tracking.gmail.message_body import _decode_data, extract_body
from tests.tracking.gmail_payloads import b64


def test_extract_body_html_top_level():
    """Top-level text/html payload is decoded."""
    payload = {"mimeType": "text/html", "body": {"data": b64("<p>Hi</p>")}}
    assert "Hi" in extract_body(payload)


def test_extract_body_multipart_skips_empty_parts_then_finds_html():
    """text/plain and text/html parts with empty data are skipped;
    the html with data is accepted.
    """
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": ""}},  # empty → skip
            {"mimeType": "text/html", "body": {"data": ""}},  # empty → skip
            {"mimeType": "text/html", "body": {"data": b64("<b>real</b>")}},
        ],
    }
    assert "real" in extract_body(payload)


def test_extract_body_recurses_into_nested_multipart():
    """Nested multipart is resolved via recursion."""
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [{"mimeType": "text/plain", "body": {"data": b64("nested body")}}],
            }
        ],
    }
    assert "nested body" in extract_body(payload)


def test_extract_body_unknown_mime_returns_empty():
    assert extract_body({"mimeType": "application/pdf", "body": {}}) == ""


def test_decode_data_invalid_base64_returns_empty():
    """Invalid Base64 → '' without raising."""
    assert _decode_data("!!!notbase64@@@") == ""


def test_extract_body_multipart_unresolvable_returns_empty():
    """Parts that don't resolve to text → recursion ends without finding anything."""
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [{"mimeType": "application/octet-stream", "body": {}}],
    }
    assert extract_body(payload) == ""
