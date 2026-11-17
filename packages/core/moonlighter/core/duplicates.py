"""Finding the stored job a posting is a copy of (the key lives in core/dedup.py)."""

from dataclasses import dataclass

from moonlighter.core.db import Job
from moonlighter.core.dedup import PostingKey, normalize_text, posting_key


def find_original(company: str | None, title: str | None, description: str | None) -> Job | None:
    """The lowest-id stored job with the same key that is not itself a copy; None without a key.

    A job whose posting is known to be gone (closed_at set) is no original: the same text
    posted again is a live repost, scored on its own and the original of later copies.
    """
    key = posting_key(company, title, description)
    if key is None:
        return None
    candidates = (
        Job.select()
        .where(
            Job.description_hash == key.description_hash,
            Job.duplicate_of.is_null(),
            Job.closed_at.is_null(),
        )
        .order_by(Job.id)
    )
    for candidate in candidates:
        if (normalize_text(candidate.company), normalize_text(candidate.title)) == (
            key.company,
            key.title,
        ):
            return candidate
    return None


@dataclass(frozen=True)
class DuplicateGroup:
    """Stored rows of one posting: the one kept, and the ones to archive against it."""

    kept: Job
    copies: list[Job]


def _rank(job: Job, applied_job_ids: set[int]) -> tuple[bool, bool, float, int]:
    # sorted() ascending: applied first, then a live row (neither archived nor known gone),
    # then the highest score, then the lowest id.
    live = job.status != "archived" and job.closed_at is None
    score = job.score if job.score is not None else float("-inf")
    return (job.id not in applied_job_ids, not live, -score, job.id)


def _by_key(jobs: list[Job]) -> list[list[Job]]:
    """The rows of each key, leaving out rows without text and rows already marked as copies."""
    by_key: dict[PostingKey, list[Job]] = {}
    for job in jobs:
        key = posting_key(job.company, job.title, job.description)
        if key is not None and job.duplicate_of_id is None:
            by_key.setdefault(key, []).append(job)
    return list(by_key.values())


def group_duplicates(jobs: list[Job], applied_job_ids: set[int]) -> list[DuplicateGroup]:
    """Groups of two or more rows with one key; an applied row is never a copy."""
    groups = []
    for members in _by_key(jobs):
        kept, *rest = sorted(members, key=lambda job: _rank(job, applied_job_ids))
        copies = [job for job in rest if job.id not in applied_job_ids]
        if copies:
            groups.append(DuplicateGroup(kept, copies))
    return groups
