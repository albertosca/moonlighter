"""
Monitor de email para candidaturas.

Monitora candidaturas@gmail.com, classifica respostas com LLM
e atualiza o pipeline de candidaturas automaticamente.
"""
import base64
import datetime
import json
import logging
import os
import re

from candidatador.parsing import _extract_json

logger = logging.getLogger(__name__)

# ── Importações opcionais Google (só necessárias em runtime real) ─────────────
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    Credentials = None
    Request = None
    build = None

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    InstalledAppFlow = None

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Ordem canônica de avanço no funil (não pode regredir)
_STATUS_ORDER = ["draft", "submitted", "screening", "interviews", "offer", "rejected"]

_TYPE_TO_STATUS = {
    "screening": "screening",
    "interview": "interviews",
    "offer": "offer",
    "rejection": "rejected",
    # info_request e unrelated → mantém status atual
}


class GmailAuthError(Exception):
    pass


# ── Funções públicas ──────────────────────────────────────────────────────────

def extract_ref(to_field: str, base_address: str) -> str | None:
    """
    Extrai o ref de um alias Gmail (+ref) no campo To.

    "candidaturas+x7k2mp@gmail.com" → "x7k2mp"
    Retorna None se não houver alias ou se não bater com base_address.
    """
    if not to_field:
        return None

    local, _, domain = base_address.partition("@")

    # Varre todos os endereços no campo To (pode ter múltiplos)
    for part in re.split(r",\s*", to_field):
        # Remove display name: "Nome <email>" → "email"
        m = re.search(r"<([^>]+)>", part)
        addr = m.group(1).strip() if m else part.strip()

        addr_local, _, addr_domain = addr.partition("@")
        if addr_domain.lower() != domain.lower():
            continue

        # Verifica se há +ref
        if "+" not in addr_local:
            continue

        base_local, _, ref = addr_local.partition("+")
        if base_local.lower() == local.lower() and ref:
            return ref

    return None


def setup_gmail_service(config: dict):
    """
    Carrega credentials + token OAuth2 e retorna o resource do Gmail API.

    Levanta GmailAuthError com mensagem clara se token não existe.
    Faz refresh automático se expirado.
    """
    if Credentials is None or build is None:
        raise GmailAuthError(
            "google-api-python-client não instalado. "
            "Rode: pip install google-api-python-client google-auth-oauthlib"
            " e depois setup_email() para autorizar o acesso."
        )

    token_path = os.path.expanduser(config["email"]["token_path"])

    if not os.path.exists(token_path):
        raise GmailAuthError(
            "Token Gmail não encontrado. Rode setup_email() primeiro para autorizar o acesso."
        )

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def fetch_unread_messages(service, max_results: int = 50) -> list[dict]:
    """
    Busca emails não lidos na inbox.

    Retorna lista de {id, threadId}.
    """
    response = service.users().messages().list(
        userId="me",
        labelIds=["INBOX", "UNREAD"],
        maxResults=max_results,
    ).execute()
    return response.get("messages", [])


def parse_message(service, message_id: str) -> dict:
    """
    Extrai to, from_, subject, body de uma mensagem Gmail.

    Prefere text/plain; cai para text/html se necessário.
    """
    raw = service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()

    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

    body = _extract_body(payload)

    return {
        "to": headers.get("to", ""),
        "from_": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "body": body,
    }


def _extract_body(payload: dict) -> str:
    """Extrai corpo da mensagem, preferindo text/plain sobre text/html."""
    mime = payload.get("mimeType", "")

    if mime == "text/plain":
        return _decode_data(payload.get("body", {}).get("data", ""))

    if mime == "text/html":
        return _decode_data(payload.get("body", {}).get("data", ""))

    if mime.startswith("multipart/"):
        parts = payload.get("parts", [])
        # Primeiro passa: procura text/plain
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    return _decode_data(data)
        # Segundo passa: aceita text/html
        for part in parts:
            if part.get("mimeType") == "text/html":
                data = part.get("body", {}).get("data", "")
                if data:
                    return _decode_data(data)
        # Recursão para parts aninhados (multipart dentro de multipart)
        for part in parts:
            result = _extract_body(part)
            if result:
                return result

    return ""


def _decode_data(data: str) -> str:
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:
        return ""


def mark_processed(service, message_id: str, label_id: str) -> None:
    """Marca como lido e aplica label 'candidatador/processado'."""
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={
            "removeLabelIds": ["UNREAD"],
            "addLabelIds": [label_id],
        },
    ).execute()


async def classify_response(
    message: dict, stages: list[str], llm_caller, model: str = "claude-sonnet-4-6"
) -> dict:
    """
    Classifica uma resposta de email usando LLM.

    Retorna dict com: type, stage, new_stage, company, job_title, summary.
    Em caso de falha de parsing, retorna type='unrelated'.
    """
    stages_str = ", ".join(stages)
    prompt = f"""Você é um assistente que analisa emails de processo seletivo.

Email recebido:
De: {message.get('from_', '')}
Assunto: {message.get('subject', '')}
Corpo:
{message.get('body', '')[:3000]}

Estágios conhecidos: {stages_str}

Classifique este email e retorne JSON com exatamente estes campos:
{{
  "type": "rejection"|"interview"|"screening"|"offer"|"info_request"|"unrelated",
  "stage": "<slug do estágio se type for interview ou screening, caso contrário null>",
  "new_stage": "<slug novo se o estágio não estiver na lista acima, caso contrário null>",
  "company": "<nome da empresa ou null>",
  "job_title": "<cargo ou null>",
  "summary": "<resumo em uma frase do que o email diz>"
}}

Responda APENAS com o JSON, sem texto adicional."""

    try:
        raw = await llm_caller(prompt, model)
        cleaned = _extract_json(raw)
        result = json.loads(cleaned)
        # Garante que todos os campos existem
        return {
            "type": result.get("type", "unrelated"),
            "stage": result.get("stage"),
            "new_stage": result.get("new_stage"),
            "company": result.get("company"),
            "job_title": result.get("job_title"),
            "summary": result.get("summary", ""),
        }
    except Exception as e:
        logger.warning("classify_response: falha ao parsear LLM response: %s", e)
        return {
            "type": "unrelated",
            "stage": None,
            "new_stage": None,
            "company": None,
            "job_title": None,
            "summary": "",
        }


def _get_or_create_label(service, label_name: str) -> str:
    """Retorna o ID do label, criando-o se necessário."""
    labels = service.users().labels().list(userId="me").execute()
    for label in labels.get("labels", []):
        if label["name"] == label_name:
            return label["id"]
    created = service.users().labels().create(
        userId="me",
        body={"name": label_name, "labelListVisibility": "labelShow",
              "messageListVisibility": "show"},
    ).execute()
    return created["id"]


def _status_rank(status: str) -> int:
    try:
        return _STATUS_ORDER.index(status)
    except ValueError:
        return -1


async def sync_responses(config: dict, llm_caller) -> list[dict]:
    """
    Orquestra o fluxo completo: lê emails, classifica, atualiza banco.

    Retorna lista de dicts descrevendo cada update feito.
    """
    from candidatador.db import Application, ProcessedEmail

    service = setup_gmail_service(config)
    email_cfg = config["email"]
    base_address = email_cfg["address"]
    processed_label_name = email_cfg.get("processed_label", "candidatador/processado")
    stages = list(email_cfg.get("interview_stages", []))
    model = config.get("llm_model", "claude-sonnet-4-6")

    # Por padrão o sync é 100% LEITURA no Gmail: o dedup é feito numa tabela local
    # (ProcessedEmail). Só escreve no Gmail (marca lido + label) se mark_processed=True.
    mutate_gmail = bool(email_cfg.get("mark_processed", False))
    label_id = _get_or_create_label(service, processed_label_name) if mutate_gmail else None

    def _record_done(mid: str) -> None:
        ProcessedEmail.get_or_create(message_id=mid)
        if mutate_gmail and label_id:
            mark_processed(service, mid, label_id)

    raw_messages = fetch_unread_messages(service)
    updates = []

    for msg_ref in raw_messages:
        msg_id = msg_ref["id"]
        # Já processado numa rodada anterior? pula sem reprocessar (sem re-chamar o LLM).
        if ProcessedEmail.select().where(ProcessedEmail.message_id == msg_id).exists():
            continue
        message = parse_message(service, msg_id)

        classification = await classify_response(message, stages, llm_caller, model)
        msg_type = classification["type"]

        if msg_type == "unrelated":
            _record_done(msg_id)
            continue

        # Adiciona stage novo ao config se o LLM propôs um inédito
        new_stage = classification.get("new_stage")
        if new_stage and new_stage not in stages:
            stages.append(new_stage)
            email_cfg["interview_stages"] = stages

        # Resolve qual Application atualizar
        ref = extract_ref(message["to"], base_address)
        app, match_type = _resolve_application(ref, classification)

        if app is None:
            # Sem match — registra como incerto e segue
            updates.append({
                "company": classification.get("company"),
                "title": classification.get("job_title"),
                "type": msg_type,
                "stage": classification.get("stage"),
                "match_type": "incerto",
                "summary": classification.get("summary", ""),
            })
            _record_done(msg_id)
            continue

        # Atualiza status (só avança no funil)
        new_status = _TYPE_TO_STATUS.get(msg_type)
        if new_status:
            current_rank = _status_rank(app.status)
            new_rank = _status_rank(new_status)
            if new_rank > current_rank:
                app.status = new_status

        # Atualiza stage se aplicável
        if classification.get("stage"):
            app.current_stage = classification["stage"]

        # Append note com data e match_type
        today = datetime.date.today().strftime("%Y-%m-%d")
        note = (
            f"[{today}] {msg_type}: {classification.get('summary', '')} "
            f"(match: {match_type})"
        )
        app.notes = (app.notes + "\n" + note) if app.notes else note
        app.updated_at = datetime.datetime.now()
        app.save()

        updates.append({
            "company": classification.get("company"),
            "title": classification.get("job_title"),
            "type": msg_type,
            "stage": classification.get("stage"),
            "match_type": match_type,
            "summary": classification.get("summary", ""),
        })

        _record_done(msg_id)

    return updates


def _resolve_application(ref: str | None, classification: dict):
    """
    Tenta encontrar a Application correspondente.

    Retorna (Application | None, match_type).
    match_type: 'ref' | 'fuzzy' | 'incerto'
    """
    from candidatador.db import Application, Job

    # 1. Match direto pelo ref
    if ref:
        try:
            app = Application.get(Application.email_ref == ref)
            return app, "ref"
        except Application.DoesNotExist:
            pass

    # 2. Fuzzy match: empresa + cargo com status ativo (submitted/screening/interviews)
    company = classification.get("company")
    job_title = classification.get("job_title")

    if company or job_title:
        active_statuses = ["submitted", "screening", "interviews", "offer"]
        query = (
            Application
            .select(Application, Job)
            .join(Job)
            .where(Application.status.in_(active_statuses))
        )
        if company:
            query = query.where(Job.company ** f"%{company}%")
        if job_title:
            query = query.where(Job.title ** f"%{job_title}%")

        results = list(query)
        if len(results) == 1:
            return results[0], "fuzzy"
        elif len(results) > 1:
            # Ambíguo — não atualiza nenhuma
            return None, "incerto"

    return None, "incerto"


def _run_gmail_oauth(credentials_path: str, token_path: str) -> None:
    """Executa o fluxo OAuth2 interativo e salva o token."""
    if InstalledAppFlow is None:
        raise GmailAuthError(
            "google-auth-oauthlib não instalado. "
            "Rode: pip install google-auth-oauthlib"
        )
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)
    os.makedirs(os.path.dirname(os.path.expanduser(token_path)), exist_ok=True)
    with open(os.path.expanduser(token_path), "w") as f:
        f.write(creds.to_json())


# ── Entry point standalone ────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    import sys
    import logging

    # Loga só para stdout. No cron, a saída é redirecionada para o arquivo de log
    # (>> email-sync.log), então um FileHandler aqui duplicaria cada linha.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    from candidatador.config import load_config
    from candidatador.llm import make_caller
    from candidatador.db import init_db

    init_db()  # garante conexão + tabelas (inclui ProcessedEmail) no path standalone/cron
    cfg = load_config()
    llm_caller = make_caller(cfg)

    updates = asyncio.run(sync_responses(cfg, llm_caller))
    logger.info("sync_responses: %d atualizações", len(updates))
    for u in updates:
        logger.info("  %s @ %s → %s (match: %s)", u.get("title"), u.get("company"),
                    u.get("type"), u.get("match_type"))
