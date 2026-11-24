"""Jobs a person hands over by hand: `add_job` scores and saves a posting from its URL."""

from dataclasses import dataclass, replace
from typing import Any

from moonlighter.core.config.model import Config
from moonlighter.core.db import Job
from moonlighter.core.duplicates import find_original
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.web.posting import fetch_description, fetch_posting_via_ats
from moonlighter.core.web.urls import normalize_job_url
from moonlighter.discovery.evaluation.models import EvalInput
from moonlighter.discovery.evaluation.single import evaluate_job
from moonlighter.discovery.evaluation.title_filter import should_skip_by_title
from moonlighter.discovery.manual.messages import existing_job_message, format_add_result
from moonlighter.discovery.scan.claims import claim_url
from moonlighter.discovery.scan.persistence import (
    archived_fields,
    create_job,
    duplicate_fields,
    scored_fields,
)
from moonlighter.discovery.screening.evaluator_inputs import model_for
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


def _answer_without_scoring(posting: _Posting, config: Config, *, track: bool) -> str | None:
    """The answer when no evaluation is needed, else None. A tracked job skips the title filter."""
    if not posting.company or not posting.title:
        return "Provide at least 'company' and 'title' along with the URL."
    already = existing_job_message(posting.url)
    if already:
        return already
    original = find_original(posting.company, posting.title, posting.description)
    if original is not None:
        return _store_copy(posting, original, track=track)
    if track:
        return None
    matched = should_skip_by_title(posting.title, config.get("title_blocklist", []))
    if matched:
        _persist_manual(posting, **archived_fields(f"title filtered: {matched!r}"))
        return f"Job discarded by the title filter (pattern: {matched!r})."
    return None


def _store_copy(posting: _Posting, original: Job, *, track: bool) -> str:
    _persist_manual(posting, **duplicate_fields(original.id))
    answer = (
        f"Copy of job #{original.id} ({original.company}/{original.title}): "
        "saved as an archived duplicate, not scored."
    )
    if track:
        answer += f" Track the original instead: register_application(job_id={original.id})."
    return answer


async def _score_and_store(
    posting: _Posting,
    config: Config,
    profile: dict[str, Any],
    *,
    caller: LLMCaller,
    track: bool,
) -> str:
    threshold = config["score_threshold"]
    result = await evaluate_job(
        EvalInput(
            posting.company,
            posting.title,
            posting.description,
            location=posting.location,
            remote_type=posting.remote_type,
        ),
        profile,
        model=model_for(config),
        caller=caller,
    )
    fields = scored_fields(result, threshold)
    if track:
        # The person already chose this job: the score is kept for the record, never acted on.
        fields["status"] = "reviewed"
    job = _persist_manual(posting, **fields)
    if job is None:
        return "Job already in the database (URL conflict)."
    return format_add_result(
        job, result, threshold=threshold, status=fields["status"], tracked=track
    )


async def add_job(  # noqa: PLR0913, PLR0917 - the MCP tool takes these seven fields as its public arguments
    url: str,
    company: str,
    title: str,
    description: str,
    config: Config,
    profile: dict[str, Any],
    caller: LLMCaller,
    *,
    track: bool = False,
) -> str:
    """Score and save one posting from its URL, filling what is missing from the ATS or the page."""
    url = normalize_job_url(url)
    posting = await _complete_from_ats(_Posting(company, title, url, description, None, None))
    if not posting.description:
        fetched, error = await fetch_description(url)
        if error:
            return error
        posting = replace(posting, description=fetched or "")
    answer = _answer_without_scoring(posting, config, track=track)
    if answer:
        return answer
    return await _score_and_store(posting, config, profile, caller=caller, track=track)
