"""Writing Gmail, only when the operator opts in: the processed label and archiving."""

from typing import Any


def archive_message(service: Any, message_id: str) -> None:
    """Marks read and archives (removes UNREAD and INBOX).

    Program C's post-sync cleanup, gated by the email.archive_* flags upstream.
    """
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD", "INBOX"]},
    ).execute()


def mark_processed(service: Any, message_id: str, label_id: str) -> None:
    """Marks as read and applies the 'moonlighter/processed' label."""
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"], "addLabelIds": [label_id]},
    ).execute()


def get_or_create_label(service: Any, label_name: str) -> str:
    """Returns the label's ID, creating it if it doesn't exist yet."""
    labels = service.users().labels().list(userId="me").execute()
    for label in labels.get("labels", []):
        if label["name"] == label_name:
            return str(label["id"])
    created = (
        service.users()
        .labels()
        .create(
            userId="me",
            body={
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        .execute()
    )
    return str(created["id"])
