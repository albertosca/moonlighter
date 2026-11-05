"""Jobs a person hands over by hand: `add_job` for a URL, `verify_job` for a pasted page."""

from dataclasses import dataclass, replace
from typing import Any

from moonlighter.core.db import Job
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.posting import fetch_description, fetch_posting_via_ats
from moonlighter.core.urls import normalize_job_url
from moonlighter.discovery.claims import claim_url
from moonlighter.discovery.evaluation.single import evaluate_job
from moonlighter.discovery.evaluation.title_filter import should_skip_by_title
from moonlighter.discovery.evaluator_inputs import (
    MINIMUM_DESCRIPTION_LENGTH,
    is_description_insufficient,
    model_for,
)
from moonlighter.discovery.manual_messages import existing_job_message, format_add_result
from moonlighter.discovery.persistence import archived_fields, create_job, scored_fields
from moonlighter.discovery.sources.base import normalize_remote_type


@dataclass(frozen=True)
class _Posting:
    """What add_job knows about the posting, from the person and from the ATS."""

    company: str
    title: str
    url: str
    description: str
    location: str | None
    remote_type: str | None


async def _complete_from_ats(given: _Posting) -> _Posting:
    # Always asked, even when every field was given: the ATS API is where the
    # structured location comes from, and the evaluator's regional filter needs
    # it. What the person gave still wins over the API's copy.
    found = await fetch_posting_via_ats(given.url)
    if found is None:
        return given
    return _Posting(
        company=given.company or found.company or "",
        title=given.title or found.title or "",
        url=given.url,
        description=given.description or found.description or "",
        location=found.location,
        remote_type="remote" if found.remote else normalize_remote_type(found.location),
    )


def _persist_manual(posting: _Posting, **scoring: Any) -> Job | None:
    """Save a manual job (source='manual') plus the claim in ScanLog.

    None if the URL already exists (race/conflict).
    """
    job = create_job(
        source="manual",
        company=posting.company,
        title=posting.title,
        url=posting.url,
        location=posting.location,
        remote_type=posting.remote_type,
        description=posting.description,
        posted_at=None,
        **scoring,
    )
    if job is not None and not claim_url(posting.url, "manual"):
        return None
    return job


def _answer_without_scoring(posting: _Posting, config: dict[str, Any]) -> str | None:
    """The answer when no evaluation is needed, else None."""
    if not posting.company or not posting.title:
        return "Provide at least 'company' and 'title' along with the URL."
    already = existing_job_message(posting.url)
    if already:
        return already
    matched = should_skip_by_title(posting.title, config.get("title_blocklist", []))
    if matched:
        _persist_manual(posting, **archived_fields(f"title filtered: {matched!r}"))
        return f"Job discarded by the title filter (pattern: {matched!r})."
    return None


async def _score_and_store(
    posting: _Posting, config: dict[str, Any], profile: dict[str, Any], *, caller: LLMCaller
) -> str:
    threshold = config["score_threshold"]
    result = await evaluate_job(
        company=posting.company,
        title=posting.title,
        description=posting.description,
        profile=profile,
        model=model_for(config),
        _caller=caller,
        location=posting.location,
        remote_type=posting.remote_type,
    )
    fields = scored_fields(result, threshold)
    job = _persist_manual(posting, **fields)
    if job is None:
        return "Job already in the database (URL conflict)."
    return format_add_result(job, result, threshold=threshold, status=fields["status"])


async def add_job(  # noqa: PLR0913, PLR0917 - the MCP tool's seven fields; see the backlog item
    url: str,
    company: str,
    title: str,
    description: str,
    config: dict[str, Any],
    profile: dict[str, Any],
    caller: LLMCaller,
) -> str:
    """Score and save one posting from its URL, filling what is missing from the ATS or the page."""
    url = normalize_job_url(url)
    posting = await _complete_from_ats(_Posting(company, title, url, description, None, None))
    if not posting.description:
        fetched, error = await fetch_description(url)
        if error:
            return error
        posting = replace(posting, description=fetched or "")
    answer = _answer_without_scoring(posting, config)
    if answer:
        return answer
    return await _score_and_store(posting, config, profile, caller=caller)


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
