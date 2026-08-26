"""Turn a job into a sheet the candidate can paste into the form."""

from typing import Any

import httpx
from moonlighter.application.answers.email_alias import (
    build_email_alias,
    is_email_label,
    new_email_ref,
)
from moonlighter.application.assisted.composer import ComposedAnswer, compose_answers
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sheet import render_sheet
from moonlighter.application.assisted.sources.greenhouse import (
    board_and_job_from_url,
    fetch_greenhouse_questions,
)
from moonlighter.application.assisted.sources.pasted import extract_questions_from_page
from moonlighter.application.assisted.sources.recruitee import (
    fetch_recruitee_questions,
    host_and_offer_from_url,
)
from moonlighter.application.cvgen.service import ensure_tailored_cv
from moonlighter.core.db import Application, Job
from moonlighter.core.llm import make_caller

PASTE_HINT = (
    "No form questions could be read for this job.\n"
    "Open {url}, select the whole page (Cmd+A), copy it (Cmd+C), and call\n"
    'prepare_application_from_paste({job_id}, "<the copied text>").'
)


def _job(job_id: int) -> Job | None:
    return Job.get_or_none(Job.id == job_id)


async def _questions_from_api(job: Job) -> list[FormQuestion]:
    async with httpx.AsyncClient(timeout=20) as client:
        # Keyed on the URL, not job.source: add_job stores source='manual' even
        # for a recognizable Greenhouse URL, and the regex demands a
        # greenhouse.io host, so a false positive cannot happen. (Recruitee
        # stays source-gated below — its /o/ pattern matches any host.)
        if found := board_and_job_from_url(job.url):
            return await fetch_greenhouse_questions(found[0], found[1], client)
        if job.source == "recruitee" and (found := host_and_offer_from_url(job.url)):
            return await fetch_recruitee_questions(found[0], found[1], client)
    return []


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


async def _sheet(
    job: Job, questions: list[FormQuestion], config: dict[str, Any], profile: dict[str, Any]
) -> str:
    tailored = await ensure_tailored_cv(
        {"id": job.id, "title": job.title, "company": job.company, "description": job.description},
        config,
        profile,
        make_caller(config),
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
        make_caller(config),
    )
    alias = _tracking_alias(job, config)
    if alias is not None:
        composed = _with_tracking_alias(composed, alias)
    sheet = render_sheet(composed, job_title=job.title, company=job.company, apply_url=job.url)
    if alias is not None and not any(_takes_alias(item.question) for item in composed):
        # No email question reached the sheet (a paste that missed it, a source
        # that omits standard fields) — the alias must reach the operator anyway,
        # or the company's reply lands in a mailbox the monitor never reads.
        sheet += f"\n\nWhere the form asks for an email address, use: {alias}"
    if tailored is not None and not tailored.compiled:
        sheet += (
            f"\n\nA tailored CV was generated but pdflatex is not installed —"
            f" compile it yourself: cd {tailored.path.parent} && pdflatex {tailored.path.name}"
        )
    return sheet


async def prepare_application(job_id: int, config: dict[str, Any], profile: dict[str, Any]) -> str:
    job = _job(job_id)
    if job is None:
        return f"Job {job_id} not found."
    questions = await _questions_from_api(job)
    if not questions:
        return PASTE_HINT.format(url=job.url, job_id=job_id)
    return await _sheet(job, questions, config, profile)


async def prepare_application_from_paste(
    job_id: int, page_text: str, config: dict[str, Any], profile: dict[str, Any]
) -> str:
    job = _job(job_id)
    if job is None:
        return f"Job {job_id} not found."
    questions = await extract_questions_from_page(page_text, make_caller(config))
    if not questions:
        return "No questions could be found in that text. Was the whole page copied?"
    return await _sheet(job, questions, config, profile)
