"""Re-scoring a needs_review job from the text a person pasted from its page."""

from typing import Any

from moonlighter.core.db import Job
from moonlighter.core.duplicates import find_original
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.discovery.evaluation.models import EvalInput
from moonlighter.discovery.evaluation.single import evaluate_job
from moonlighter.discovery.manual.messages import format_add_result
from moonlighter.discovery.scan.persistence import duplicate_fields, scored_fields
from moonlighter.discovery.screening.evaluator_inputs import (
    MINIMUM_DESCRIPTION_LENGTH,
    is_description_insufficient,
    model_for,
)


def _archive_if_copy(job: Job, page_text: str) -> str | None:
    """Archive the job against a stored twin of the pasted text, without an LLM call."""
    original = find_original(job.company, job.title, page_text)
    if original is None or original.id == job.id:
        return None
    job.description = page_text
    for name, value in duplicate_fields(original.id).items():
        setattr(job, name, value)
    job.save()
    return (
        f"Job #{job.id} is a copy of job #{original.id} ({original.company}/{original.title}): "
        "archived as a duplicate, not scored."
    )


async def verify_job(
    job_id: int,
    page_text: str,
    config: dict[str, Any],
    *,
    profile: dict[str, Any],
    caller: LLMCaller,
) -> str:
    """Re-score a job flagged needs_review (empty description) using text pasted from its page.

    Updates the same row in place.
    """
    try:
        job = Job.get_by_id(job_id)
    except Job.DoesNotExist:
        return f"Job #{job_id} not found."
    if job.status != "needs_review":
        return f"Job #{job_id} is not pending verification (status: {job.status!r})."

    if is_description_insufficient(page_text):
        return (
            f"That paste is too short to score ({len(page_text.strip())} chars — need at least "
            f"{MINIMUM_DESCRIPTION_LENGTH}). Job #{job_id} stays pending — open {job.url} "
            "and copy the whole page."
        )

    copy_answer = _archive_if_copy(job, page_text)
    if copy_answer is not None:
        return copy_answer
    threshold = config["score_threshold"]
    result = await evaluate_job(
        EvalInput(
            job.company, job.title, page_text, location=job.location, remote_type=job.remote_type
        ),
        profile,
        model=model_for(config),
        caller=caller,
    )
    fields = scored_fields(result, threshold)
    job.description = page_text
    for name, value in fields.items():
        setattr(job, name, value)
    job.save()
    return format_add_result(job, result, threshold=threshold, status=fields["status"])
