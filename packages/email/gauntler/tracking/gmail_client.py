"""
Gmail API surface: authentication, message fetch/parse, label management.
"""

import base64
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Optional Google imports (only needed at real runtime) ───────────────────
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
except ImportError:  # pragma: no cover - optional import fallback (google libs)
    Credentials = None  # type: ignore[assignment, misc]
    Request = None  # type: ignore[assignment, misc]
    build = None

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:  # pragma: no cover - optional import fallback (oauthlib)
    InstalledAppFlow = None

SCOPE_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_MODIFY = "https://www.googleapis.com/auth/gmail.modify"


class GmailAuthError(Exception):
    pass


# ── Gmail API: authentication and reading ───────────────────────────────────


def _required_scope(config: dict[str, Any]) -> str:
    """gmail.modify only when the operator opts into marking messages
    read/labeled (email.mark_processed=true); readonly by default — the sync
    is 100% read-only save for that opt-in (S-08, least-privilege principle)."""
    email_cfg = config.get("email", {})
    return SCOPE_MODIFY if email_cfg.get("mark_processed", False) else SCOPE_READONLY


def _warn_if_scope_mismatch(creds: Any, required_scope: str) -> None:
    """The saved token may carry a broader scope than currently needed
    (e.g. an old token with gmail.modify when mark_processed=false only needs
    gmail.readonly). Never revokes on its own — just warns, once, clearly
    (S-08). Defensive: only acts if .scopes is actually a real sequence."""
    granted = getattr(creds, "scopes", None)
    if not isinstance(granted, (list, set, tuple)):
        return
    granted_set = set(granted)
    if required_scope not in granted_set and SCOPE_MODIFY in granted_set:
        logger.warning(
            "Gmail token has a broader scope (%s) than required (%s). "
            "Run setup_email() to re-consent with the minimal scope.",
            ", ".join(sorted(granted_set)),
            required_scope,
        )


def setup_gmail_service(config: dict[str, Any]) -> Any:
    """Loads credentials + OAuth2 token and returns the Gmail API resource.
    Raises GmailAuthError with a clear message if the token doesn't exist; refreshes
    automatically if expired."""
    if Credentials is None or build is None:
        raise GmailAuthError(
            "google-api-python-client not installed. "
            "Run: pip install google-api-python-client google-auth-oauthlib"
            " and then setup_email() to authorize access."
        )

    token_path = Path(config["email"]["token_path"]).expanduser()
    if not token_path.exists():
        raise GmailAuthError("Gmail token not found. Run setup_email() first to authorize access.")

    required_scope = _required_scope(config)
    creds = Credentials.from_authorized_user_file(str(token_path), [required_scope])  # type: ignore[no-untyped-call]
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())

    _warn_if_scope_mismatch(creds, required_scope)
    return build("gmail", "v1", credentials=creds)


def fetch_unread_messages(service: Any, max_results: int = 50) -> list[dict[str, Any]]:
    """Fetches unread emails in the inbox. Returns a list of {id, threadId}."""
    response = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_results)
        .execute()
    )
    messages: list[dict[str, Any]] = response.get("messages", [])
    return messages


def parse_message(service: Any, message_id: str) -> dict[str, Any]:
    """Extracts to, from_, subject, body from a Gmail message."""
    raw = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    return {
        "to": headers.get("to", ""),
        "from_": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "body": _extract_body(payload),
    }


def _extract_body(payload: dict[str, Any]) -> str:
    """Extracts the message body, preferring text/plain over text/html."""
    mime = payload.get("mimeType", "")
    if mime in ("text/plain", "text/html"):
        return _decode_data(payload.get("body", {}).get("data", ""))
    if mime.startswith("multipart/"):
        return _extract_multipart(payload.get("parts", []))
    return ""


def _extract_multipart(parts: list[dict[str, Any]]) -> str:
    """Looks for the body in a multipart message: text/plain first, then text/html,
    and finally recurses into nested parts (multipart within multipart)."""
    for preferred in ("text/plain", "text/html"):
        for part in parts:
            if part.get("mimeType") == preferred:
                data = part.get("body", {}).get("data", "")
                if data:
                    return _decode_data(data)
    for part in parts:
        body = _extract_body(part)
        if body:
            return body
    return ""


def _decode_data(data: str) -> str:
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:
        return ""


def mark_processed(service: Any, message_id: str, label_id: str) -> None:
    """Marks as read and applies the 'gauntler/processed' label."""
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"], "addLabelIds": [label_id]},
    ).execute()


def _get_or_create_label(service: Any, label_name: str) -> str:
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


def _run_gmail_oauth(
    credentials_path: str, token_path: str, config: dict[str, Any] | None = None
) -> None:
    """Runs the interactive OAuth2 flow and saves the token."""
    if InstalledAppFlow is None:
        raise GmailAuthError(
            "google-auth-oauthlib not installed. Run: pip install google-auth-oauthlib"
        )
    scope = _required_scope(config or {})
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, [scope])
    creds = flow.run_local_server(port=0)
    expanded = Path(token_path).expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    expanded.write_text(creds.to_json())
    expanded.chmod(0o600)
