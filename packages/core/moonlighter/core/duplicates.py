"""Finding the stored job a posting is a copy of (the key lives in core/dedup.py)."""

from moonlighter.core.db import Job
from moonlighter.core.dedup import normalize_text, posting_key


def find_original(company: str | None, title: str | None, description: str | None) -> Job | None:
    """The lowest-id stored job with the same key that is not itself a copy; None without a key."""
    key = posting_key(company, title, description)
    if key is None:
        return None
    candidates = (
        Job.select()
        .where(Job.description_hash == key.description_hash, Job.duplicate_of.is_null())
        .order_by(Job.id)
    )
    for candidate in candidates:
        if (normalize_text(candidate.company), normalize_text(candidate.title)) == (
            key.company,
            key.title,
        ):
            return candidate
    return None
