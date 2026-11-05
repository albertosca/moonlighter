"""Parsing a Gmail message into the fields a reply is classified on."""

from unittest.mock import MagicMock

from moonlighter.tracking.gmail.messages import parse_message

from tests.tracking.gmail_payloads import b64
from tests.tracking.tracking_settings import BASE_EMAIL


def _build_gmail_message(
    *, to_address: str, from_: str, subject: str, body: str, content_type: str = "text/plain"
) -> dict:
    """Builds a Gmail API message structure."""
    return {
        "id": "msg123",
        "payload": {
            "headers": [
                {"name": "To", "value": to_address},
                {"name": "From", "value": from_},
                {"name": "Subject", "value": subject},
            ],
            "mimeType": content_type,
            "body": {"data": b64(body)},
        },
    }


class TestParseMessage:
    def test_extracts_plain_text_body(self):
        raw_message = _build_gmail_message(
            to_address=BASE_EMAIL,
            from_="hr@company.com",
            subject="Update",
            body="Congratulations, you moved forward!",
            content_type="text/plain",
        )
        service = MagicMock()
        service.users().messages().get().execute.return_value = raw_message

        result = parse_message(service, "msg123")

        assert result["to"] == BASE_EMAIL
        assert result["from_"] == "hr@company.com"
        assert result["subject"] == "Update"
        assert "Congratulations" in result["body"]

    def test_falls_back_to_html_when_no_plain(self):
        raw_message = {
            "id": "msg456",
            "payload": {
                "headers": [
                    {"name": "To", "value": BASE_EMAIL},
                    {"name": "From", "value": "noreply@co.com"},
                    {"name": "Subject", "value": "HTML only"},
                ],
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {"data": b64("<p>Hello!</p>")},
                    }
                ],
            },
        }
        service = MagicMock()
        service.users().messages().get().execute.return_value = raw_message

        result = parse_message(service, "msg456")
        assert "Hello" in result["body"]

    def test_prefers_plain_over_html_in_multipart(self):
        raw_message = {
            "id": "msg789",
            "payload": {
                "headers": [
                    {"name": "To", "value": BASE_EMAIL},
                    {"name": "From", "value": "noreply@co.com"},
                    {"name": "Subject", "value": "Multipart"},
                ],
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": b64("Texto puro")},
                    },
                    {
                        "mimeType": "text/html",
                        "body": {"data": b64("<p>HTML</p>")},
                    },
                ],
            },
        }
        service = MagicMock()
        service.users().messages().get().execute.return_value = raw_message

        result = parse_message(service, "msg789")
        assert result["body"] == "Texto puro"

    def test_handles_missing_body_gracefully(self):
        raw_message = {
            "id": "msg000",
            "payload": {
                "headers": [
                    {"name": "To", "value": BASE_EMAIL},
                    {"name": "From", "value": "x@y.com"},
                    {"name": "Subject", "value": "Empty"},
                ],
                "mimeType": "text/plain",
                "body": {},
            },
        }
        service = MagicMock()
        service.users().messages().get().execute.return_value = raw_message

        result = parse_message(service, "msg000")
        assert result["body"] == ""
