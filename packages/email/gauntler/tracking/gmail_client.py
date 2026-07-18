"""
Gmail API surface: authentication, message fetch/parse, label management.
"""

import base64
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Importações opcionais Google (só necessárias em runtime real) ─────────────
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
except ImportError:  # pragma: no cover - fallback de import opcional (libs google)
    Credentials = None  # type: ignore[assignment, misc]
    Request = None  # type: ignore[assignment, misc]
    build = None

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:  # pragma: no cover - fallback de import opcional (oauthlib)
    InstalledAppFlow = None

SCOPE_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_MODIFY = "https://www.googleapis.com/auth/gmail.modify"


class GmailAuthError(Exception):
    pass


# ── Gmail API: autenticação e leitura ───────────────────────────────────────


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
            "Gmail token tem escopo mais amplo (%s) do que o necessário (%s). "
            "Rode setup_email() para re-consentir com o escopo mínimo.",
            ", ".join(sorted(granted_set)),
            required_scope,
        )


def setup_gmail_service(config: dict[str, Any]) -> Any:
    """Carrega credentials + token OAuth2 e devolve o resource do Gmail API.
    Levanta GmailAuthError com mensagem clara se o token não existe; faz refresh
    automático se expirado."""
    if Credentials is None or build is None:
        raise GmailAuthError(
            "google-api-python-client não instalado. "
            "Rode: pip install google-api-python-client google-auth-oauthlib"
            " e depois setup_email() para autorizar o acesso."
        )

    token_path = Path(config["email"]["token_path"]).expanduser()
    if not token_path.exists():
        raise GmailAuthError(
            "Token Gmail não encontrado. Rode setup_email() primeiro para autorizar o acesso."
        )

    required_scope = _required_scope(config)
    creds = Credentials.from_authorized_user_file(str(token_path), [required_scope])  # type: ignore[no-untyped-call]
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())

    _warn_if_scope_mismatch(creds, required_scope)
    return build("gmail", "v1", credentials=creds)


def fetch_unread_messages(service: Any, max_results: int = 50) -> list[dict[str, Any]]:
    """Busca emails não lidos na inbox. Devolve lista de {id, threadId}."""
    response = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_results)
        .execute()
    )
    messages: list[dict[str, Any]] = response.get("messages", [])
    return messages


def parse_message(service: Any, message_id: str) -> dict[str, Any]:
    """Extrai to, from_, subject, body de uma mensagem Gmail."""
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
    """Extrai o corpo da mensagem, preferindo text/plain a text/html."""
    mime = payload.get("mimeType", "")
    if mime in ("text/plain", "text/html"):
        return _decode_data(payload.get("body", {}).get("data", ""))
    if mime.startswith("multipart/"):
        return _extract_multipart(payload.get("parts", []))
    return ""


def _extract_multipart(parts: list[dict[str, Any]]) -> str:
    """Procura o corpo num multipart: text/plain primeiro, text/html depois, e por
    fim desce recursivamente em parts aninhados (multipart dentro de multipart)."""
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
    """Marca como lido e aplica o label 'gauntler/processed'."""
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"], "addLabelIds": [label_id]},
    ).execute()


def _get_or_create_label(service: Any, label_name: str) -> str:
    """Devolve o ID do label, criando-o se ainda não existir."""
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
    """Executa o fluxo OAuth2 interativo e salva o token."""
    if InstalledAppFlow is None:
        raise GmailAuthError(
            "google-auth-oauthlib não instalado. Rode: pip install google-auth-oauthlib"
        )
    scope = _required_scope(config or {})
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, [scope])
    creds = flow.run_local_server(port=0)
    expanded = Path(token_path).expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    expanded.write_text(creds.to_json())
    expanded.chmod(0o600)
