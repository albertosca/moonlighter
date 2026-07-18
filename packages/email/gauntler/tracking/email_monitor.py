"""
Monitor de email para candidaturas.

Monitora candidaturas@gmail.com, classifica respostas com LLM
e atualiza o pipeline de candidaturas automaticamente.
"""

import datetime
import logging
import re
from typing import Any

from gauntler.core.llm import LLMCaller
from gauntler.tracking.classification import classify_response
from gauntler.tracking.gmail_client import (
    _get_or_create_label,
    fetch_unread_messages,
    mark_processed,
    parse_message,
    setup_gmail_service,
)

logger = logging.getLogger(__name__)

# Ordem canônica de avanço no funil — o status só anda para frente, nunca regride.
_STATUS_ORDER = ["draft", "submitted", "screening", "interviews", "offer", "rejected"]
_ACTIVE_STATUSES = ["submitted", "screening", "interviews", "offer"]

_TYPE_TO_STATUS = {
    "screening": "screening",
    "interview": "interviews",
    "offer": "offer",
    "rejection": "rejected",
    # info_request e unrelated → mantém status atual
}


def extract_ref(to_field: str, base_address: str) -> str | None:
    """Extrai o ref de um alias Gmail (+ref) no campo To.

    "candidaturas+x7k2mp@gmail.com" → "x7k2mp"
    None se não houver alias ou se não bater com base_address."""
    if not to_field:
        return None

    local, _, domain = base_address.partition("@")
    for part in re.split(r",\s*", to_field):  # o campo To pode ter vários endereços
        match = re.search(r"<([^>]+)>", part)  # "Nome <email>" → "email"
        addr = match.group(1).strip() if match else part.strip()

        addr_local, _, addr_domain = addr.partition("@")
        if addr_domain.lower() != domain.lower() or "+" not in addr_local:
            continue
        base_local, _, ref = addr_local.partition("+")
        if base_local.lower() == local.lower() and ref:
            return ref

    return None


# ── Sync: lê, classifica e atualiza o pipeline ──────────────────────────────


async def sync_responses(config: dict[str, Any], llm_caller: LLMCaller) -> list[dict[str, Any]]:
    """Orquestra o fluxo completo: lê emails não lidos, classifica e atualiza o
    banco. Devolve a lista de updates feitos."""
    from gauntler.core.db import ProcessedEmail

    service = setup_gmail_service(config)
    email_cfg = config["email"]
    base_address = email_cfg["address"]
    stages = list(email_cfg.get("interview_stages", []))
    model = config.get("llm_model", "claude-sonnet-4-6")

    # O sync é 100% LEITURA no Gmail por padrão: o dedup vive numa tabela local
    # (ProcessedEmail). Só escreve no Gmail (lido + label) se mark_processed=True.
    mutate_gmail = bool(email_cfg.get("mark_processed", False))
    label_name = email_cfg.get("processed_label", "gauntler/processed")
    label_id = _get_or_create_label(service, label_name) if mutate_gmail else None

    def mark_done(message_id: str) -> None:
        ProcessedEmail.get_or_create(message_id=message_id)
        if mutate_gmail and label_id:
            mark_processed(service, message_id, label_id)

    updates = []
    for msg_ref in fetch_unread_messages(service):
        msg_id = msg_ref["id"]
        if ProcessedEmail.select().where(ProcessedEmail.message_id == msg_id).exists():
            continue  # já processado numa rodada anterior — não re-chama o LLM

        message = parse_message(service, msg_id)
        classification = await classify_response(message, stages, llm_caller, model)
        if classification["type"] == "unrelated":
            mark_done(msg_id)
            continue

        ref = extract_ref(message["to"], base_address)
        app, match_type = _resolve_application(ref, classification)
        if app is not None and match_type == "ref":
            _register_new_stage(classification.get("new_stage"), stages, email_cfg)
            _advance_application(app, classification, match_type, stages)
            updates.append(_make_update(classification, match_type))
        elif app is not None:  # match_type == "fuzzy" — suggestion only (S-06)
            updates.append(_make_suggestion(app, classification, match_type))
        else:
            updates.append(_make_update(classification, "incerto"))
        mark_done(msg_id)

    return updates


_MAX_STAGE_LEN = 40
_MAX_STAGES = 40

_STAGE_ALLOWED = re.compile(r"[^a-z0-9]+")


def _sanitize_stage(raw: str | None) -> str | None:
    """Normalize an LLM-proposed stage to a bounded ``[a-z0-9_]`` slug.

    An email is untrusted input: a prompt-injected classification can propose an
    arbitrary ``new_stage``. Reducing it to a lowercase snake_case slug of at most
    ``_MAX_STAGE_LEN`` chars strips special characters and bounds length, so a
    persisted stage cannot carry a payload back into a later prompt. Snake_case
    matches this project's stage naming convention (e.g. ``phone_screening``),
    so a newly registered stage matches the same email's ``stage`` value. Returns
    ``None`` when nothing usable remains or the slug is over-length.
    """
    if not raw:
        return None
    slug = _STAGE_ALLOWED.sub("_", raw.lower()).strip("_")
    if not slug or len(slug) > _MAX_STAGE_LEN:
        return None
    return slug


def _register_new_stage(
    new_stage: str | None, stages: list[str], email_cfg: dict[str, Any]
) -> None:
    """Learn a novel stage proposed by the LLM, persisting it to the in-memory config.

    The candidate is sanitized to a bounded slug (untrusted email input) and only
    registered while the stage list is below ``_MAX_STAGES``, so a hostile email
    cannot inject arbitrary text or grow the config without bound.
    """
    slug = _sanitize_stage(new_stage)
    if slug is None or slug in stages or len(stages) >= _MAX_STAGES:
        return
    stages.append(slug)
    email_cfg["interview_stages"] = stages


def _advance_application(
    app: Any, classification: dict[str, Any], match_type: str, stages: list[str]
) -> None:
    """Advances the Application through the funnel (forward only) and notes
    the event.

    current_stage is only written if the value is in the list of known stages
    (which already includes any new_stage legitimately registered by
    _register_new_stage BEFORE this call) — a stage outside that list is
    hallucination/injection and is silently discarded (S-05)."""
    new_status = _TYPE_TO_STATUS.get(classification["type"])
    if new_status and _status_rank(new_status) > _status_rank(app.status):
        app.status = new_status
    stage = classification.get("stage")
    if stage and stage in stages:
        app.current_stage = stage

    today = datetime.date.today().strftime("%Y-%m-%d")
    summary = classification.get("summary", "")
    note = f"[{today}] {classification['type']}: {summary} (match: {match_type})"
    app.notes = f"{app.notes}\n{note}" if app.notes else note
    app.updated_at = datetime.datetime.now()
    app.save()


def _make_update(classification: dict[str, Any], match_type: str) -> dict[str, Any]:
    return {
        "company": classification.get("company"),
        "title": classification.get("job_title"),
        "type": classification["type"],
        "stage": classification.get("stage"),
        "match_type": match_type,
        "summary": classification.get("summary", ""),
    }


def _make_suggestion(app: Any, classification: dict[str, Any], match_type: str) -> dict[str, Any]:
    """Fuzzy-match suggestion — never mutates the Application, only signals
    for human review via update_status (S-06)."""
    update = _make_update(classification, match_type)
    update["suggested_job_id"] = app.job_id
    update["needs_confirmation"] = True
    return update


def _status_rank(status: str) -> int:
    try:
        return _STATUS_ORDER.index(status)
    except ValueError:
        return -1


def _resolve_application(ref: str | None, classification: dict[str, Any]) -> tuple[Any, str]:
    """Encontra a Application correspondente, por ref (exato) ou empresa+cargo
    (fuzzy). Devolve (Application | None, 'ref' | 'fuzzy' | 'incerto')."""
    if ref:
        app = _match_by_ref(ref)
        if app is not None:
            return app, "ref"

    app = _match_by_company_title(classification.get("company"), classification.get("job_title"))
    if app is not None:
        return app, "fuzzy"
    return None, "incerto"


def _match_by_ref(ref: str) -> Any:
    from gauntler.core.db import Application

    try:
        return Application.get(Application.email_ref == ref)
    except Application.DoesNotExist:
        return None


def _match_by_company_title(company: str | None, job_title: str | None) -> Any:
    """Match fuzzy entre candidaturas ativas. Devolve a Application única, ou None
    quando não há candidato ou quando é ambíguo (>1 — não dá para decidir)."""
    if not (company or job_title):
        return None

    from gauntler.core.db import Application, Job

    query = (
        Application.select(Application, Job)
        .join(Job)
        .where(Application.status.in_(_ACTIVE_STATUSES))
    )
    if company:
        query = query.where(Job.company ** f"%{company}%")
    if job_title:
        query = query.where(Job.title ** f"%{job_title}%")

    results = list(query)
    return results[0] if len(results) == 1 else None


# ── Entry point standalone ────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    import logging
    import sys

    # Loga só para stdout. No cron, a saída é redirecionada para o arquivo de log
    # (>> email-sync.log), então um FileHandler aqui duplicaria cada linha.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    from gauntler.core.config import load_config
    from gauntler.core.db import init_db
    from gauntler.core.llm import make_caller

    init_db()  # garante conexão + tabelas (inclui ProcessedEmail) no path standalone/cron
    cfg = load_config()
    llm_caller = make_caller(cfg)

    updates = asyncio.run(sync_responses(cfg, llm_caller))
    logger.info("sync_responses: %d atualizações", len(updates))
    for u in updates:
        logger.info(
            "  %s @ %s → %s (match: %s)",
            u.get("title"),
            u.get("company"),
            u.get("type"),
            u.get("match_type"),
        )
