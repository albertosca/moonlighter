"""Email monitor for job applications.

Monitor the configured Gmail account, classify replies with the LLM,
and automatically update the applications pipeline.
"""

import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from moonlighter.core.config.defaults import DEFAULT_LLM_MODEL
from moonlighter.core.db import ProcessedEmail
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.spend_limit import is_spend_limit
from moonlighter.core.metrics import record_spend_limit_hit
from moonlighter.tracking.gmail.client import setup_gmail_service
from moonlighter.tracking.gmail.labels import archive_message, get_or_create_label, mark_processed
from moonlighter.tracking.gmail.messages import fetch_recent_messages, parse_message
from moonlighter.tracking.sync.application_matching import extract_ref, resolve_application
from moonlighter.tracking.sync.classification import classify_response
from moonlighter.tracking.sync.funnel import advance_application
from moonlighter.tracking.sync.interview_stages import register_new_stage
from moonlighter.tracking.sync.report import make_suggestion, make_update

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = DEFAULT_LLM_MODEL


@dataclass(frozen=True)
class _SyncSettings:
    """What one sync reads from the config, with the one stage list every message shares."""

    email_config: dict[str, Any]
    base_address: str
    stages: list[str]
    model: str
    archive_all: bool
    archive_reference_matched: bool


@dataclass(frozen=True)
class _GmailHandles:
    """The Gmail resource, and the processed label when the operator opted into writes."""

    service: Any
    mutate_gmail: bool
    label_id: str | None


class _SpendLimitReachedError(Exception):
    """Stops the sync: the quota is spent, so the rest of the batch waits for the next run."""


async def sync_responses(config: dict[str, Any], llm_caller: LLMCaller) -> list[dict[str, Any]]:
    """Run the full flow: read recent emails, classify them, and update the database.

    Returns the list of updates made.
    """
    service = setup_gmail_service(config)
    email_config = config["email"]
    settings = _read_settings(config, email_config)
    gmail = _gmail_handles(service, email_config)

    updates = []
    with suppress(_SpendLimitReachedError):
        for message_reference in fetch_recent_messages(
            service, int(email_config.get("lookback_days", 30))
        ):
            update = await _sync_message(
                message_reference["id"], gmail, settings, llm_caller=llm_caller
            )
            if update is not None:
                updates.append(update)

    return updates


def _read_settings(config: dict[str, Any], email_config: dict[str, Any]) -> _SyncSettings:
    archive_all = bool(email_config.get("archive_all_classified", False))
    return _SyncSettings(
        email_config=email_config,
        base_address=email_config["address"],
        stages=list(email_config.get("interview_stages", [])),
        model=config.get("llm_model", _DEFAULT_MODEL),
        archive_all=archive_all,
        # Layer two is a superset of layer one by design.
        archive_reference_matched=archive_all
        or bool(email_config.get("archive_ref_matched", False)),
    )


def _gmail_handles(service: Any, email_config: dict[str, Any]) -> _GmailHandles:
    # The sync is 100% READ-ONLY on Gmail by default: dedup lives in a local table
    # (ProcessedEmail). Only writes to Gmail (read + label) if mark_processed=True.
    mutate_gmail = bool(email_config.get("mark_processed", False))
    label_name = email_config.get("processed_label", "moonlighter/processed")
    label_id = get_or_create_label(service, label_name) if mutate_gmail else None
    return _GmailHandles(service=service, mutate_gmail=mutate_gmail, label_id=label_id)


async def _sync_message(
    message_id: str, gmail: _GmailHandles, settings: _SyncSettings, *, llm_caller: LLMCaller
) -> dict[str, Any] | None:
    """Classifies one message and applies it; returns its report entry, or None when it has none."""
    if ProcessedEmail.select().where(ProcessedEmail.message_id == message_id).exists():
        return None  # already processed in a previous run — don't re-call the LLM

    message = parse_message(gmail.service, message_id)
    classification = await _classify(message_id, message, settings, llm_caller=llm_caller)
    if classification is None:
        return None

    if classification["type"] == "unrelated":
        _mark_done(gmail, message_id)
        return None

    update, archivable = _apply_reply(message, classification, settings)
    _archive(gmail, message_id, eligible=archivable)
    _mark_done(gmail, message_id)
    return update


async def _classify(
    message_id: str, message: dict[str, Any], settings: _SyncSettings, *, llm_caller: LLMCaller
) -> dict[str, Any] | None:
    """The classification, or None to leave the message for the next run.

    Raises _SpendLimitReachedError when the quota is spent, which stops the sync.
    """
    try:
        return await classify_response(message, settings.stages, llm_caller, model=settings.model)
    except Exception as error:  # any classification failure leaves the message for the next run
        if is_spend_limit(error):
            record_spend_limit_hit()
            logger.warning(
                "sync_responses: spend limit hit while classifying %s — stopping sync "
                "early, leaving it and the rest of this batch unprocessed for the next run",
                message_id,
            )
            raise _SpendLimitReachedError from error
        logger.warning(
            "sync_responses: classification failed for %s — leaving it unprocessed "
            "for the next run: %s",
            message_id,
            error,
        )
        return None  # NOT mark_done: a failed classification must not burn the message


def _apply_reply(
    message: dict[str, Any], classification: dict[str, Any], settings: _SyncSettings
) -> tuple[dict[str, Any], bool]:
    """Applies a classified reply to its application; returns its entry and whether to archive."""
    reference = extract_ref(message["to"], settings.base_address)
    application, match_type = resolve_application(reference, classification)
    if application is not None and match_type == "ref":
        register_new_stage(classification.get("new_stage"), settings.stages, settings.email_config)
        advanced = advance_application(
            application, classification, match_type, stages=settings.stages
        )
        update = make_update(classification, match_type, application, status_advanced=advanced)
        return update, settings.archive_reference_matched
    if application is not None:  # match_type == "fuzzy" — suggestion only (S-06)
        return make_suggestion(application, classification, match_type), settings.archive_all
    return make_update(classification, "uncertain"), settings.archive_all


def _archive(gmail: _GmailHandles, message_id: str, *, eligible: bool) -> None:
    """A Gmail archive failure must never cost the pipeline update that already applied.

    Warn and move on.
    """
    if not eligible:
        return
    try:
        archive_message(gmail.service, message_id)
    except Exception as error:  # noqa: BLE001 - an archive failure must not stop the sync; the message is still recorded
        logger.warning("sync_responses: could not archive %s — %s", message_id, error)


def _mark_done(gmail: _GmailHandles, message_id: str) -> None:
    ProcessedEmail.get_or_create(message_id=message_id)
    if gmail.mutate_gmail and gmail.label_id:
        mark_processed(gmail.service, message_id, gmail.label_id)
