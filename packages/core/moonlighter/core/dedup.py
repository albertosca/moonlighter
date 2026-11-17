"""The content key that says two postings are the same job, whatever their URLs.

Recruitee mints a new slug per duplicate offer, so the URL alone let one posting
become many jobs (Tether: 236 rows for 65 titles, 2026-11-16). The key is the
normalized company, the normalized title and a hash of the normalized text.
Empty text proves nothing, so it never yields a key.
"""

import hashlib
import re
from dataclasses import dataclass
from html import unescape

_TAG = re.compile(r"<[^>]+>")
_NON_WORD_RUN = re.compile(r"[\W_]+")


def normalize_text(text: str | None) -> str:
    """Lowercase, without HTML tags, every run of whitespace or punctuation as one space."""
    if not text:
        return ""
    without_tags = _TAG.sub(" ", unescape(text))
    return _NON_WORD_RUN.sub(" ", without_tags.lower()).strip()


def description_hash(description: str | None) -> str | None:
    """sha256 of the normalized text; None when nothing is left after normalizing."""
    normalized = normalize_text(description)
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode()).hexdigest()


@dataclass(frozen=True)
class PostingKey:
    """What two postings must share to be one job."""

    company: str
    title: str
    description_hash: str


def posting_key(
    company: str | None, title: str | None, description: str | None
) -> PostingKey | None:
    """The group key of a posting; None when its description is empty."""
    digest = description_hash(description)
    if digest is None:
        return None
    return PostingKey(normalize_text(company), normalize_text(title), digest)
