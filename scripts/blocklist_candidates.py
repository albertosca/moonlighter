"""The jobs build_blocklist learns from: archived jobs a real evaluation scored low.

Notes that mark a job as never genuinely evaluated are left out. The prefixes `title filtered`
and `reevaluate_error` are the ones scripts/reevaluation_records.py writes; `evaluation error`
is what a failed evaluation stores.
"""

from moonlighter.core.db import Job


def fetch_low_scorers(threshold: float, company: str | None) -> dict[str, list[str]]:
    """Returns {company: [title, ...]} for archived jobs with 0 < score <= threshold."""
    query = (
        Job.select(Job.company, Job.title)
        .where(
            Job.score > 0,
            Job.score <= threshold,
            Job.status == "archived",
            Job.score_notes.is_null(is_null=False),
            ~Job.score_notes.startswith("evaluation error"),
            ~Job.score_notes.startswith("title filtered"),
            ~Job.score_notes.startswith("reevaluate_error"),
        )
        .order_by(Job.company, Job.title)
    )
    if company:
        query = query.where(Job.company == company)

    grouped: dict[str, list[str]] = {}
    for job in query:
        grouped.setdefault(job.company, []).append(job.title)
    return grouped
