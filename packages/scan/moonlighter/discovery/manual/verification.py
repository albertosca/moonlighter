"""Re-scoring a needs_review job from the text a person pasted from its page."""

from typing import Any

from moonlighter.core.db import Job
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.discovery.evaluation.single import evaluate_job
from moonlighter.discovery.manual.messages import format_add_result
from moonlighter.discovery.scan.persistence import scored_fields
from moonlighter.discovery.screening.evaluator_inputs import (
    MINIMUM_DESCRIPTION_LENGTH,
    is_description_insufficient,
    model_for,
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

    threshold = config["score_threshold"]
    result = await evaluate_job(
        company=job.company,
        title=job.title,
        description=page_text,
        profile=profile,
        model=model_for(config),
        _caller=caller,
        location=job.location,
        remote_type=job.remote_type,
    )
    fields = scored_fields(result, threshold)
    job.description = page_text
    for name, value in fields.items():
        setattr(job, name, value)
    job.save()
    return format_add_result(job, result, threshold=threshold, status=fields["status"])
