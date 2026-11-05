"""Turn a job into a sheet the candidate can paste into the form."""

from typing import Any

import httpx

from moonlighter.application.answers.bank.store import load_answer_bank
from moonlighter.application.assisted.composition.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion
from moonlighter.application.assisted.sheet.bootstrap_offer import cv_bootstrap_offer
from moonlighter.application.assisted.sheet.notes import (
    alias_note,
    cv_note,
    well_shaped_form_data,
    with_tracking_alias,
)
from moonlighter.application.assisted.sheet.required_labels import mark_required
from moonlighter.application.assisted.sheet.results import SheetKind, SheetResult, failed_sheet
from moonlighter.application.assisted.sources import registry
from moonlighter.application.assisted.sources.base import (
    questions_or_empty,
    required_fields_or_empty,
)
from moonlighter.application.assisted.sources.pasted import (
    ExtractionError,
    extract_questions_from_page,
)
from moonlighter.application.cvgen.service import ensure_tailored_cv
from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.db import Application, Job
from moonlighter.core.email_alias import build_email_alias, new_email_ref
from moonlighter.core.llm.dispatch import make_caller
from moonlighter.core.log import get_logger

logger = get_logger(__name__)

PASTE_HINT = (
    "No form questions could be read for this job.\n"
    "Open {url}, select the whole page (Cmd+A), copy it (Cmd+C), and call\n"
    'prepare_application_from_paste({job_id}, "<the copied text>").'
)
PASTE_REQUIRED_LINE = "This form requires: {fields}."
SOURCE_NOTE_PASTE_IGNORED = (
    "The pasted text was not used: this job's ATS publishes its form, which is more reliable."
)


async def _api_form(job: Job) -> tuple[list[FormQuestion], tuple[str, ...]]:
    """The form from the job's ATS, or — when it has none — the fields it requires."""
    match = registry.find_match(job)
    if match is None:
        return [], ()
    async with httpx.AsyncClient(timeout=20) as client:
        questions = await questions_or_empty(match, client)
        if questions:
            return questions, ()
        return [], await required_fields_or_empty(match, client)


def _job_dict(job: Job) -> dict[str, Any]:
    """The job fields the CV tailoring and the answer composer both read."""
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "description": job.description,
    }


def _tracking_alias(application: Application, config: dict[str, Any]) -> str | None:
    """The +ref alias for this application, minting its ref on first use.

    The ref is reused forever after (a regenerated ref orphans every reply already
    sent to the old one). None when no tracking mailbox is configured — the sheet
    then keeps whatever email the field map filled in.
    """
    address = (config.get("email") or {}).get("address")
    if not address:
        return None
    if not application.email_ref:
        application.email_ref = new_email_ref()
        application.save()
    return build_email_alias(str(address), str(application.email_ref))


async def _sheet(
    job: Job,
    questions: list[FormQuestion],
    config: dict[str, Any],
    *,
    profile: dict[str, Any],
    source_note: str | None = None,
) -> SheetResult:
    application, _ = Application.get_or_create(job=job, defaults={"status": "draft"})
    job_cache: dict[str, Any] = application.get_form_data()
    answer_bank = load_answer_bank(
        config.get("answer_bank_max_age_days", DEFAULTS["answer_bank_max_age_days"])
    )
    caller = make_caller(config)
    tailored = await ensure_tailored_cv(
        _job_dict(job),
        config,
        profile,
        caller=caller,
    )
    composed = await compose_answers(
        questions,
        profile,
        config,
        {**_job_dict(job), "location": job.location, "remote_type": job.remote_type},
        caller,
        job_cache=job_cache,
        answer_bank=answer_bank,
    )
    application.form_data = well_shaped_form_data(job_cache)
    application.save()
    alias = _tracking_alias(application, config)
    if alias is not None:
        composed = with_tracking_alias(composed, alias)
    return SheetResult(
        kind=SheetKind.SHEET,
        composed=composed,
        job_title=job.title,
        company=job.company,
        apply_url=job.url,
        alias=alias,
        alias_note=alias_note(composed, alias),
        cv_note=cv_note(tailored, composed),
        cv_path=str(tailored.path) if tailored is not None else None,
        cv_compiled=tailored.compiled if tailored is not None else None,
        source_note=source_note,
    )


def _precheck(job_id: int, config: dict[str, Any]) -> Job | SheetResult:
    """The job, or the sheet that ends the request before any question is read."""
    job = Job.get_or_none(Job.id == job_id)
    if job is None:
        return failed_sheet(SheetKind.JOB_NOT_FOUND, f"Job {job_id} not found.")
    if (offer := cv_bootstrap_offer(config)) is not None:
        return offer
    return job


async def prepare_application(
    job_id: int, config: dict[str, Any], profile: dict[str, Any]
) -> SheetResult:
    """The sheet for a job, read from its ATS form; a paste hint when the ATS publishes none."""
    job = _precheck(job_id, config)
    if isinstance(job, SheetResult):
        return job
    questions, required_labels = await _api_form(job)
    if not questions:
        hint = PASTE_HINT.format(url=job.url, job_id=job_id)
        if required_labels:
            hint += "\n" + PASTE_REQUIRED_LINE.format(fields=", ".join(required_labels))
        return failed_sheet(SheetKind.NEEDS_PASTE, hint, apply_url=job.url)
    return await _sheet(job, questions, config, profile=profile)


async def prepare_application_from_paste(
    job_id: int, page_text: str, config: dict[str, Any], *, profile: dict[str, Any]
) -> SheetResult:
    """The sheet for a job whose form was pasted as page text; the ATS form wins when it has one."""
    job = _precheck(job_id, config)
    if isinstance(job, SheetResult):
        return job
    api_questions, required_labels = await _api_form(job)
    if api_questions:
        return await _sheet(
            job, api_questions, config, profile=profile, source_note=SOURCE_NOTE_PASTE_IGNORED
        )
    try:
        questions = await extract_questions_from_page(page_text, make_caller(config))
    except ExtractionError as error:
        logger.warning("paste extraction failed for job %s: %s", job.id, error)
        return failed_sheet(
            SheetKind.NO_QUESTIONS,
            "The model's reading of that text could not be used — nothing is wrong with "
            "the paste. Just run it again.",
        )
    if not questions:
        return failed_sheet(
            SheetKind.NO_QUESTIONS,
            "No questions could be found in that text. Was the whole page copied?",
        )
    if required_labels:
        questions = mark_required(questions, required_labels)
    return await _sheet(job, questions, config, profile=profile)
