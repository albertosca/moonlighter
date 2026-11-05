"""The entries sync_responses reports, one per classified reply."""

from typing import Any


def make_update(
    classification: dict[str, Any],
    match_type: str,
    application: Any = None,
    *,
    status_advanced: bool = False,
) -> dict[str, Any]:
    # A ref match already knows the exact Job; the classifier's reading of the
    # email (which rarely repeats the title) is only the fallback.
    #
    # job_id/status_advanced exist for the composition root: this package may
    # not import the answer bank (moonlighter-email depends on core alone), so
    # promotion happens in server.py and this is all it has to go on.
    job = getattr(application, "job", None)
    return {
        "job_id": getattr(application, "job_id", None),
        "status_advanced": status_advanced,
        "company": (job.company if job else None) or classification.get("company"),
        "title": (job.title if job else None) or classification.get("job_title"),
        "type": classification["type"],
        "stage": classification.get("stage"),
        "match_type": match_type,
        "summary": classification.get("summary", ""),
    }


def make_suggestion(
    application: Any, classification: dict[str, Any], match_type: str
) -> dict[str, Any]:
    """Fuzzy-match suggestion — never mutates the Application.

    It only signals for human review via update_status (S-06).
    """
    update = make_update(classification, match_type)
    update["suggested_job_id"] = application.job_id
    update["needs_confirmation"] = True
    return update
