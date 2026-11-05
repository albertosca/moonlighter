"""Gmail writes: the processed label, label lookup and archiving."""

from unittest.mock import MagicMock

from moonlighter.tracking.gmail_labels import archive_message, get_or_create_label, mark_processed


class TestMarkProcessed:
    def test_removes_unread_label_and_adds_processed_label(self):
        service = MagicMock()
        service.users().messages().modify().execute.return_value = {}

        mark_processed(service, "msg123", "Label_123")

        modify_call = service.users().messages().modify.call_args
        body = modify_call.kwargs.get("body") or modify_call.args[0] if modify_call.args else {}
        if not body and modify_call.kwargs:
            body = modify_call.kwargs.get("body", {})

        assert "UNREAD" in body.get("removeLabelIds", [])
        assert "Label_123" in body.get("addLabelIds", [])

    def test_calls_execute(self):
        service = MagicMock()
        service.users().messages().modify().execute.return_value = {}

        mark_processed(service, "msg123", "Label_xyz")

        assert service.users().messages().modify().execute.called


# ── get_or_create_label ────────────────────────────────────────────────────


def test_get_or_create_label_returns_existing():
    """Label already exists → returns the existing id."""
    service = MagicMock()
    service.users().labels().list().execute.return_value = {
        "labels": [{"name": "moonlighter/processed", "id": "Label_42"}]
    }
    assert get_or_create_label(service, "moonlighter/processed") == "Label_42"


def test_get_or_create_label_creates_when_missing():
    """Label doesn't exist → creates it and returns the new id."""
    service = MagicMock()
    service.users().labels().list().execute.return_value = {"labels": []}
    service.users().labels().create().execute.return_value = {"id": "Label_new"}
    assert get_or_create_label(service, "moonlighter/processed") == "Label_new"


def test_get_or_create_label_skips_non_matching_then_creates():
    """An existing label that doesn't match is skipped and the target is created."""
    service = MagicMock()
    service.users().labels().list().execute.return_value = {
        "labels": [{"name": "OTHER", "id": "x"}]
    }
    service.users().labels().create().execute.return_value = {"id": "Label_new"}
    assert get_or_create_label(service, "moonlighter/processed") == "Label_new"


def test_archive_message_removes_unread_and_inbox():
    service = MagicMock()
    archive_message(service, "m1")
    service.users().messages().modify.assert_called_with(
        userId="me", id="m1", body={"removeLabelIds": ["UNREAD", "INBOX"]}
    )
    service.users().messages().modify().execute.assert_called()
