"""Gmail authentication: the OAuth token, the scope it needs, and the API resource."""

import json
import logging
from pathlib import Path
from typing import Any

from moonlighter.core.config.paths import moonlighter_home, resolve_under_home

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


# ── Gmail API: authentication ───────────────────────────────────────────────


_MUTATING_FLAGS = ("mark_processed", "archive_ref_matched", "archive_all_classified")


def _required_scope(config: dict[str, Any]) -> str:
    """gmail.modify only when the operator opts into some Gmail mutation.

    That is marking processed, or the program-C archive flags; readonly by default —
    the sync is 100% read-only save for those opt-ins (S-08).
    """
    email_config = config.get("email", {})
    mutates = any(email_config.get(flag, False) for flag in _MUTATING_FLAGS)
    return SCOPE_MODIFY if mutates else SCOPE_READONLY


def _warn_if_scope_mismatch(credentials: Any, required_scope: str) -> None:
    """The saved token may carry a broader scope than currently needed.

    For example an old token with gmail.modify when mark_processed=false only needs
    gmail.readonly. Never revokes on its own — just warns, once, clearly
    (S-08). Defensive: only acts if .scopes is actually a real sequence.
    """
    granted = getattr(credentials, "scopes", None)
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
    elif required_scope == SCOPE_MODIFY and SCOPE_MODIFY not in granted_set:
        # The opposite direction: an archive/mark flag is on but the token is
        # readonly — the old message told users to re-consent DOWN, which
        # would break the very feature they enabled.
        logger.warning(
            "Gmail token lacks the scope this configuration needs (%s). "
            "Run setup_email() to re-consent and grant it.",
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
        return [str(granted_scope) for granted_scope in scopes]
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
    automatically if expired.
    """
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
    token_path = resolve_under_home(token_path_raw)
    if not token_path.exists():
        raise GmailAuthError("Gmail token not found. Run setup_email() first to authorize access.")

    required_scope = _required_scope(config)
    # Send the scopes the grant actually carries; _warn_if_scope_mismatch is what
    # flags a token broader than we need. Narrowing here is not a privilege
    # reduction — it just makes the refresh fail.
    scopes = _token_scopes(token_path) or [required_scope]
    credentials = Credentials.from_authorized_user_file(str(token_path), scopes)  # type: ignore[no-untyped-call]
    if not credentials.valid and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        # Persist only a token file we own. `token_path` may point at another
        # project's file — that is a supported setup, and how this account's
        # credential is kept alive today. google-auth's serialisation would
        # rewrite that file's shape (a `scopes` list where the owner keeps a
        # `scope` string, plus expiry and universe_domain) and can break the
        # owner. Refreshing in memory costs one request per sync.
        if _is_ours(token_path):
            token_path.write_text(credentials.to_json())
        else:
            logger.debug("token at %s belongs to another project — not writing back", token_path)

    _warn_if_scope_mismatch(credentials, required_scope)
    return build("gmail", "v1", credentials=credentials)


def run_gmail_oauth(
    credentials_path: str, token_path: str, config: dict[str, Any] | None = None
) -> None:
    """Runs the interactive OAuth2 flow and saves the token."""
    if InstalledAppFlow is None:
        raise GmailAuthError(
            "google-auth-oauthlib not installed. Run: pip install google-auth-oauthlib"
        )
    scope = _required_scope(config or {})
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, [scope])
    credentials = flow.run_local_server(port=0)
    expanded = Path(token_path).expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    expanded.write_text(credentials.to_json())
    expanded.chmod(0o600)
