"""Turn a job into a sheet the candidate can paste into the form."""

from typing import Any, cast

import httpx
from moonlighter.application.assisted.composer import compose_answers
from moonlighter.application.assisted.questions import FormQuestion
from moonlighter.application.assisted.sheet import render_sheet
from moonlighter.application.assisted.sources.greenhouse import (
    board_and_job_from_url,
    fetch_greenhouse_questions,
)
from moonlighter.application.assisted.sources.pasted import extract_questions_from_page
from moonlighter.application.assisted.sources.recruitee import (
    fetch_recruitee_questions,
    slug_and_offer_from_url,
)
from moonlighter.core.db import Job
from moonlighter.core.llm import make_caller

PASTE_HINT = (
    "No form questions could be read for this job.\n"
    "Open {url}, select the whole page (Cmd+A), copy it (Cmd+C), and call\n"
    'prepare_application_from_paste({job_id}, "<the copied text>").'
)


def _job(job_id: int) -> Job | None:
    return cast(Job | None, Job.get_or_none(Job.id == job_id))


async def _questions_from_api(job: Job) -> list[FormQuestion]:
    async with httpx.AsyncClient(timeout=20) as client:
        if job.source == "greenhouse" and (found := board_and_job_from_url(job.url)):
            return await fetch_greenhouse_questions(found[0], found[1], client)
        if job.source == "recruitee" and (found := slug_and_offer_from_url(job.url)):
            return await fetch_recruitee_questions(found[0], found[1], client)
    return []


async def _sheet(
    job: Job, questions: list[FormQuestion], config: dict[str, Any], profile: dict[str, Any]
) -> str:
    composed = await compose_answers(
        questions,
        profile,
        config,
        {
            "title": job.title,
            "company": job.company,
            "description": job.description,
            "location": job.location,
            "remote_type": job.remote_type,
        },
        make_caller(config),
    )
    return render_sheet(composed, job_title=job.title, company=job.company, apply_url=job.url)


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
