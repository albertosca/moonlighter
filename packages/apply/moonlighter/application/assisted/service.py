"""Turn a job into a sheet the candidate can paste into the form."""

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
from moonlighter.application.answers.answer_bank import load_answer_bank
from moonlighter.application.assisted.composer import ComposedAnswer, compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.results import SheetKind, SheetResult
from moonlighter.application.assisted.sources import registry
from moonlighter.application.assisted.sources.base import (
    questions_or_empty,
    required_fields_or_empty,
)
from moonlighter.application.assisted.sources.pasted import (
    ExtractionError,
    extract_questions_from_page,
)
from moonlighter.application.cvgen.service import ensure_tailored_cv, resolved_pool_path
from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.db import Application, Job, cv_bootstrap_declined
from moonlighter.core.email_alias import (
    build_email_alias,
    is_email_label,
    new_email_ref,
)
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

# Keywords that tie a required-field label (from a source's required_fields)
# to a question read from a paste, matched as whole words, EN and PT-BR.
_REQUIRED_KEYWORDS: dict[str, tuple[str, ...]] = {
    "LinkedIn": ("linkedin",),
    "Salary expectation": (
        "salary",
        "salário",
        "salario",
        "salarial",
        "pretensão",
        "pretensao",
        "remuneração",
        "remuneracao",
    ),
    "CV": ("cv", "currículo", "curriculo", "curriculum", "resume", "résumé"),
    "Location": ("location", "localização", "localizacao", "cidade"),
}


def _job(job_id: int) -> Job | None:
    return Job.get_or_none(Job.id == job_id)


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


def _mark_required(
    questions: list[FormQuestion], required_labels: tuple[str, ...]
) -> list[FormQuestion]:
    keywords = [
        keyword
        for label in required_labels
        for keyword in _REQUIRED_KEYWORDS.get(label, (label.lower(),))
    ]
    patterns = [re.compile(rf"\b{re.escape(keyword)}\b") for keyword in keywords]
    return [
        replace(question, required=True)
        if not question.required
        and any(pattern.search(question.label.lower()) for pattern in patterns)
        else question
        for question in questions
    ]


def _tracking_alias(job: Job, config: dict[str, Any]) -> str | None:
    """The +ref alias for this application, minting the draft Application row on
    first use and reusing its ref forever after (a regenerated ref orphans every
    reply already sent to the old one). None when no tracking mailbox is
    configured — the sheet then keeps whatever email the field map filled in."""
    address = (config.get("email") or {}).get("address")
    if not address:
        return None
    application, _ = Application.get_or_create(job=job, defaults={"status": "draft"})
    if not application.email_ref:
        application.email_ref = new_email_ref()
        application.save()
    return build_email_alias(str(address), str(application.email_ref))


def _takes_alias(question: FormQuestion) -> bool:
    return (
        is_email_label(question.label)
        and not question.is_choice
        and question.kind is not QuestionKind.FILE
    )


def _with_tracking_alias(composed: list[ComposedAnswer], alias: str) -> list[ComposedAnswer]:
    """The alias answers every email field — including one the composer left as a
    gap: tracking must not depend on the profile carrying an email address."""
    return [
        ComposedAnswer(item.question, alias, None) if _takes_alias(item.question) else item
        for item in composed
    ]


def _well_shaped(entry: Any) -> bool:
    """Whether a per-job cache entry has this feature's {"answer": str, "kind": str}
    shape. Rows written by the removed browser-automation tool are a flat
    label->string mapping instead (8 of them in the live DB). compose_answers
    ignores those on read but cannot remove them; dropping them here lets the
    row self-heal into the new shape the first time a sheet is prepared,
    instead of carrying the legacy junk forward forever."""
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("answer"), str)
        and isinstance(entry.get("kind"), str)
    )


def _names_path(composed: list[ComposedAnswer], path: Path) -> bool:
    """Whether some gap already tells the operator to upload this exact file."""
    return any(item.gap_reason is not None and str(path) in item.gap_reason for item in composed)


async def _sheet(
    job: Job,
    questions: list[FormQuestion],
    config: dict[str, Any],
    profile: dict[str, Any],
    *,
    source_note: str | None = None,
) -> SheetResult:
    application, _ = Application.get_or_create(job=job, defaults={"status": "draft"})
    job_cache: dict[str, Any] = application.get_form_data()
    answer_bank = load_answer_bank(
        config.get("answer_bank_max_age_days", DEFAULTS["answer_bank_max_age_days"])
    )
    caller = make_caller(config)
    tailored = await ensure_tailored_cv(
        {"id": job.id, "title": job.title, "company": job.company, "description": job.description},
        config,
        profile,
        caller,
    )
    composed = await compose_answers(
        questions,
        profile,
        config,
        {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "description": job.description,
            "location": job.location,
            "remote_type": job.remote_type,
        },
        caller,
        job_cache=job_cache,
        answer_bank=answer_bank,
    )
    application.form_data = json.dumps(
        {label: value for label, value in job_cache.items() if _well_shaped(value)}
    )
    application.save()
    alias = _tracking_alias(job, config)
    if alias is not None:
        composed = _with_tracking_alias(composed, alias)
    alias_note = None
    if alias is not None and not any(_takes_alias(item.question) for item in composed):
        # No email question reached the sheet (a paste that missed it, a source
        # that omits standard fields) — the alias must reach the operator anyway,
        # or the company's reply lands in a mailbox the monitor never reads.
        alias_note = f"Where the form asks for an email address, use: {alias}"
    cv_note = None
    if tailored is not None and not tailored.compiled:
        # The CV gap names the DEFAULT CV here (resolve_cv_path refuses a dir
        # with no pdf), so "compile it" alone leaves the operator compiling a
        # tailored CV and then uploading the generic one.
        cv_note = (
            f"A tailored CV was generated but pdflatex is not installed —"
            f" compile it yourself: cd {tailored.path.parent} && pdflatex {tailored.path.name}"
            f" — then upload the resulting cv.pdf instead of the CV named above"
            f" (review it first)"
        )
    if tailored is not None and tailored.compiled and not _names_path(composed, tailored.path):
        # Same shape as the alias footer above: the compiled CV otherwise
        # surfaces only through the composer's CV FILE branch, which needs a
        # FILE question with a CV-shaped label. A paste that missed the resume
        # field would leave a tailored PDF nobody is told to review or upload.
        cv_note = (
            f"Upload this CV for this job: {tailored.path}"
            f" (tailored for this job — review it before uploading)"
        )
    return SheetResult(
        kind=SheetKind.SHEET,
        composed=composed,
        job_title=job.title,
        company=job.company,
        apply_url=job.url,
        alias=alias,
        alias_note=alias_note,
        cv_note=cv_note,
        cv_path=str(tailored.path) if tailored is not None else None,
        cv_compiled=tailored.compiled if tailored is not None else None,
        source_note=source_note,
    )


def failed_sheet(kind: SheetKind, message: str, *, apply_url: str = "") -> SheetResult:
    """A sheet that never got past an early check: no job, no questions.

    The empty title/company are what the renderer's error short-circuit
    ignores, so they carry no information. apply_url defaults empty too (no
    job in hand for JOB_NOT_FOUND/NO_QUESTIONS) but the NEEDS_PASTE call site
    passes job.url explicitly: a script reading apply_url off that result
    needs the URL to open and paste from, and PASTE_HINT already has it.
    """
    return SheetResult(
        kind=kind, composed=[], job_title="", company="", apply_url=apply_url, error=message
    )


_CV_BOOTSTRAP_OFFER_MESSAGE = (
    "You don't have a tailored-CV pool yet. I can draft one from your profile.yaml — "
    "call the bootstrap_cv_pool tool to generate it, or skip_cv_bootstrap if you'd "
    "rather not use this feature. I'll keep offering this on every "
    "prepare_application until you either bootstrap a pool or skip it. "
    "From a shell: `moonlighter-apply bootstrap-cv` (add --skip to decline)."
)


def _cv_bootstrap_offer(config: dict[str, Any]) -> SheetResult | None:
    if resolved_pool_path(config).exists() or cv_bootstrap_declined():
        return None
    return failed_sheet(SheetKind.CV_BOOTSTRAP_OFFER, _CV_BOOTSTRAP_OFFER_MESSAGE)


async def prepare_application(
    job_id: int, config: dict[str, Any], profile: dict[str, Any]
) -> SheetResult:
    job = _job(job_id)
    if job is None:
        return failed_sheet(SheetKind.JOB_NOT_FOUND, f"Job {job_id} not found.")
    if (offer := _cv_bootstrap_offer(config)) is not None:
        return offer
    questions, required_labels = await _api_form(job)
    if not questions:
        hint = PASTE_HINT.format(url=job.url, job_id=job_id)
        if required_labels:
            hint += "\n" + PASTE_REQUIRED_LINE.format(fields=", ".join(required_labels))
        return failed_sheet(SheetKind.NEEDS_PASTE, hint, apply_url=job.url)
    return await _sheet(job, questions, config, profile)


async def prepare_application_from_paste(
    job_id: int, page_text: str, config: dict[str, Any], profile: dict[str, Any]
) -> SheetResult:
    job = _job(job_id)
    if job is None:
        return failed_sheet(SheetKind.JOB_NOT_FOUND, f"Job {job_id} not found.")
    if (offer := _cv_bootstrap_offer(config)) is not None:
        return offer
    api_questions, required_labels = await _api_form(job)
    if api_questions:
        return await _sheet(
            job, api_questions, config, profile, source_note=SOURCE_NOTE_PASTE_IGNORED
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
        questions = _mark_required(questions, required_labels)
    return await _sheet(job, questions, config, profile)
