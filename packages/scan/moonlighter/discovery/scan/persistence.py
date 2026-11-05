"""Saving a job with the fields its screening or scoring produced."""

import json
from typing import Any

from peewee import IntegrityError

from moonlighter.core.db import Job
from moonlighter.discovery.evaluation.models import EvaluationResult
from moonlighter.discovery.sources.base import RawJob


def create_job(**fields: Any) -> Job | None:
    """Create a Job; None if the URL already exists."""
    try:
        job: Job = Job.create(**fields)
    except IntegrityError:
        return None
    return job


def persist(raw: RawJob, **scoring: Any) -> Job | None:
    """Save the RawJob as a Job with the scoring fields; None if the URL already exists."""
    return create_job(
        source=raw.source,
        company=raw.company,
        title=raw.title,
        url=raw.url,
        location=raw.location,
        remote_type=raw.remote_type,
        description=raw.description,
        posted_at=raw.posted_at,
        **scoring,
    )


def scored_fields(result: EvaluationResult, threshold: float) -> dict[str, Any]:
    """The fields of a job the evaluator scored: new above the threshold, archived below it."""
    return {
        "score": result.score,
        "score_notes": result.score_notes,
        "caveats": json.dumps(result.caveats),
        "salary_min": result.salary_min,
        "salary_max": result.salary_max,
        "salary_currency": result.salary_currency,
        "salary_source": result.salary_source,
        "status": "new" if result.score >= threshold else "archived",
    }


def archived_fields(score_notes: str) -> dict[str, Any]:
    """The fields of a job a deterministic rule archived without an LLM call."""
    return {"score": 0.0, "score_notes": score_notes, "caveats": "[]", "status": "archived"}


def needs_review_fields(score_notes: str) -> dict[str, Any]:
    """The fields of a job that waits for a human to paste the real page."""
    return {"score": None, "score_notes": score_notes, "caveats": "[]", "status": "needs_review"}
