"""The entries sync_responses reports, one per classified reply."""

from dataclasses import KW_ONLY, asdict, dataclass, replace
from typing import Any


@dataclass(frozen=True)
class SyncUpdate:
    """One classified reply: the job it moved (if any) and what the email said.

    job_id/status_advanced exist for the composition root: this package may
    not import the answer bank (moonlighter-email depends on core alone), so
    promotion happens in server.py and this is all it has to go on.
    """

    job_id: int | None
    status_advanced: bool
    company: str | None
    title: str | None
    message_type: str
    stage: str | None
    match_type: str
    summary: str
    _: KW_ONLY
    # A fuzzy match is only a suggestion: the person confirms it with update_status.
    suggested_job_id: int | None = None
    needs_confirmation: bool = False

    @property
    def advanced_job_id(self) -> int | None:
        """The job whose answers the composition root promotes: set only when the reply moved it."""
        return self.job_id if self.status_advanced else None


def make_update(
    classification: dict[str, Any],
    match_type: str,
    application: Any = None,
    *,
    status_advanced: bool = False,
) -> SyncUpdate:
    # A ref match already knows the exact Job; the classifier's reading of the
    # email (which rarely repeats the title) is only the fallback.
    job = getattr(application, "job", None)
    return SyncUpdate(
        job_id=getattr(application, "job_id", None),
        status_advanced=status_advanced,
        company=(job.company if job else None) or classification.get("company"),
        title=(job.title if job else None) or classification.get("job_title"),
        message_type=classification["type"],
        stage=classification.get("stage"),
        match_type=match_type,
        summary=classification.get("summary", ""),
    )


def make_suggestion(
    application: Any, classification: dict[str, Any], match_type: str
) -> SyncUpdate:
    """Fuzzy-match suggestion — never mutates the Application.

    It only signals for human review via update_status (S-06).
    """
    return replace(
        make_update(classification, match_type),
        suggested_job_id=application.job_id,
        needs_confirmation=True,
    )


def sync_update_to_dict(update: SyncUpdate) -> dict[str, Any]:
    """The CLI's JSON entry: the email's type under "type", suggestion keys only on a suggestion."""
    data = asdict(update)
    data["type"] = data.pop("message_type")
    if not update.needs_confirmation:
        del data["suggested_job_id"], data["needs_confirmation"]
    return {key: data[key] for key in _KEY_ORDER if key in data}


_KEY_ORDER = (
    "job_id",
    "status_advanced",
    "company",
    "title",
    "type",
    "stage",
    "match_type",
    "summary",
    "suggested_job_id",
    "needs_confirmation",
)
