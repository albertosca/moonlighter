"""The three database writes a re-evaluation run makes to a job it has looked at.

The strings persisted here are a contract with `scripts/blocklist_candidates.py`: it leaves out rows whose notes start with `title filtered` or `reevaluate_error`, so changing either prefix changes which jobs the blocklist builder proposes from.
"""

import json

from moonlighter.core.db import Job
from moonlighter.discovery.evaluation.models import EvaluationResult

ERROR_NOTES_LIMIT = 200


def record_title_skip(job_id: int, matched_pattern: str) -> None:
    """Archives the job with a score of zero and a note naming the blocklist pattern that matched."""
    Job.update(
        score=0.0,
        score_notes=f"title filtered: {matched_pattern!r}",
        caveats="[]",
        status="archived",
    ).where(Job.id == job_id).execute()


def record_error(job_id: int, error: Exception) -> None:
    """Keeps the job as it was and notes the first 200 characters of the error."""
    Job.update(score_notes=f"reevaluate_error: {str(error)[:ERROR_NOTES_LIMIT]}").where(
        Job.id == job_id
    ).execute()


def record_result(job_id: int, result: EvaluationResult, status: str) -> None:
    """Stores the evaluation's score, notes, caveats and salary fields with the status it earned."""
    Job.update(
        score=result.score,
        score_notes=result.score_notes,
        caveats=json.dumps(result.caveats),
        salary_min=result.salary_min,
        salary_max=result.salary_max,
        salary_currency=result.salary_currency,
        salary_source=result.salary_source,
        status=status,
    ).where(Job.id == job_id).execute()
