"""The texts add_job and verify_job answer with."""

from moonlighter.core.db import Job, ScanLog
from moonlighter.discovery.evaluation.models import EvaluationResult


def existing_job_message(url: str) -> str | None:
    """'Already exists' message if the URL is already in the DB; None otherwise."""
    if not ScanLog.select().where(ScanLog.job_url == url).exists():
        return None
    try:
        job = Job.get(Job.url == url)
    except Job.DoesNotExist:
        return None
    score_text = f"{job.score:.1f}" if job.score is not None else "—"
    hint = (
        " Use verify_job(job_id, page_text) to score it from the real page."
        if job.status == "needs_review"
        else ""
    )
    return (
        f"Job already in the database (id={job.id}, score={score_text}, status={job.status}).{hint}"
    )


def format_add_result(job: Job, result: EvaluationResult, *, threshold: float, status: str) -> str:
    """The scored-job answer: verdict, score, notes, caveats and the job id."""
    icon = "✓ NEW" if status == "new" else "archived"
    caveats_text = (
        "\n".join(f"  ⚠ {caveat}" for caveat in result.caveats) if result.caveats else "  none"
    )
    return (
        f"{icon} — {job.company} / {job.title}\n"
        f"Score: {result.score:.1f}/10  (threshold: {threshold})\n"
        f"Notes: {result.score_notes}\n"
        f"Caveats:\n{caveats_text}\n"
        f"id={job.id}"
    )
