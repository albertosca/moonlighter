"""
Gmail API surface: authentication, message fetch/parse, label management.
"""

import base64
import json
import logging
from pathlib import Path
from typing import Any

from moonlighter.core.config import moonlighter_home

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


def _token_scopes(token_path: Path) -> list[str] | None:
    """The scopes the token file itself declares, or None if it declares none.

    Accepts both shapes: google-auth writes a `scopes` list, while google's own
    token endpoint (and other clients) write a space-separated `scope` string.
    Reading them matters because a refresh must request the scopes actually
    granted — asking for gmail.readonly against a grant of gmail.modify fails
    with invalid_scope, since one does not literally contain the other.
    """
    try:
        data = json.loads(token_path.read_text())
    except OSError, ValueError:
        return None
    scopes = data.get("scopes")
    if isinstance(scopes, list) and scopes:
        return [str(s) for s in scopes]
    scope = data.get("scope")
    if isinstance(scope, str) and scope.strip():
        return scope.split()
    return None


def _is_ours(token_path: Path) -> bool:
    """True when the token file lives inside MOONLIGHTER_HOME, i.e. we own it."""
    try:
        return token_path.resolve().is_relative_to(moonlighter_home().resolve())
    except OSError, ValueError:
        return False


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
    # Send the scopes the grant actually carries; _warn_if_scope_mismatch is what
    # flags a token broader than we need. Narrowing here is not a privilege
    # reduction — it just makes the refresh fail.
    scopes = _token_scopes(token_path) or [required_scope]
    creds = Credentials.from_authorized_user_file(str(token_path), scopes)  # type: ignore[no-untyped-call]
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Persist only a token file we own. `token_path` may point at another
        # project's file — that is a supported setup, and how this account's
        # credential is kept alive today. google-auth's serialisation would
        # rewrite that file's shape (a `scopes` list where the owner keeps a
        # `scope` string, plus expiry and universe_domain) and can break the
        # owner. Refreshing in memory costs one request per sync.
        if _is_ours(token_path):
            token_path.write_text(creds.to_json())
        else:
            logger.debug("token at %s belongs to another project — not writing back", token_path)

    _warn_if_scope_mismatch(creds, required_scope)
    return build("gmail", "v1", credentials=creds)


def fetch_unread_messages(service: Any, max_results: int = 50) -> list[dict[str, Any]]:
    """Fetches unread emails, spam included. Returns a list of {id, threadId}.

    `in:anywhere` rather than labelIds=[INBOX, UNREAD]: SPAM is a separate label
    from INBOX, so the label filter hid every message Gmail had flagged. ATS
    confirmations sent to a plus-alias land there routinely — one did, for the
    holepunch application on 2026-08-04 — and "we received your application" is
    the single reply least worth missing.
    """
    response = (
        service.users()
        .messages()
        .list(userId="me", q="is:unread in:anywhere", maxResults=max_results)
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
    """Marks as read and applies the 'moonlighter/processed' label."""
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
