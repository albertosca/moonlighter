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

    token_path_raw = (config.get("email") or {}).get("token_path")
    if not token_path_raw:
        raise GmailAuthError(
            "email.token_path is not configured. Add an 'email:' block to "
            "config.yaml (see config.example.yaml) and run setup_email() to "
            "authorize access."
        )
    token_path = Path(token_path_raw).expanduser()
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


_MAX_PAGES = 10  # hard upper bound: 10 pages × 50/page = 500 messages per sync, max


def fetch_recent_messages(
    service: Any, lookback_days: int = 30, max_results: int = 50
) -> list[dict[str, Any]]:
    """Recent messages, whether or not they have been read. Returns a list of
    {id, threadId}.

    Read state is deliberately not part of the search: a person reads their mail, and
    a reply that has been read is exactly the reply worth recording. Re-processing is
    prevented by ProcessedEmail, not by the unread flag.

    `in:anywhere` rather than labelIds=[INBOX]: SPAM is a separate label from INBOX,
    so the label filter hid every message Gmail had flagged. ATS confirmations sent to
    a plus-alias land there routinely — one did, for the holepunch application on
    2026-08-04 — and "we received your application" is the single reply least worth
    missing.

    Paginates via nextPageToken up to _MAX_PAGES pages, so a mailbox with more than
    max_results messages inside the lookback window doesn't silently lose the older
    ones: Gmail returns newest-first and the query can't exclude already-processed
    messages, so a single unpaginated page truncates and those older messages age out
    of the window before ever being fetched — with no drain mechanism (the previous
    is:unread design had one: marking a message read removed it from the query; this
    time-window design doesn't). The page bound exists so a huge mailbox can't spin
    forever; hitting it is logged just like hitting max_results on a single page.
    """
    query = f"newer_than:{lookback_days}d in:anywhere"
    messages: list[dict[str, Any]] = []
    page_token: str | None = None
    for page in range(1, _MAX_PAGES + 1):
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=max_results,
                pageToken=page_token,
            )
            .execute()
        )
        page_messages = response.get("messages", [])
        messages.extend(page_messages)
        if len(page_messages) == max_results:
            logger.warning(
                "fetch_recent_messages: page %d returned the full %d-message cap — "
                "more messages may exist in the %dd lookback window",
                page,
                max_results,
                lookback_days,
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    else:
        logger.warning(
            "fetch_recent_messages: hit the %d-page cap (%d messages fetched) — "
            "older messages in the %dd lookback window may still be unfetched",
            _MAX_PAGES,
            len(messages),
            lookback_days,
        )
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
