"""One posting per scan: copies under other URLs never cost a second LLM call."""

from dataclasses import dataclass, field

from moonlighter.core.dedup import PostingKey, posting_key
from moonlighter.core.duplicates import find_original
from moonlighter.discovery.sources.base import RawJob


@dataclass
class _SeenKeys:
    """The keys this scan already kept, and whether each one has a stored original."""

    kept: set[PostingKey] = field(default_factory=set)
    stored: dict[PostingKey, bool] = field(default_factory=dict)

    def holds_back(self, raw: RawJob, key: PostingKey) -> bool:
        """True for a copy of a posting kept earlier in this scan that has no stored row yet."""
        if key not in self.kept:
            self.kept.add(key)
            return False
        if key not in self.stored:
            self.stored[key] = find_original(raw.company, raw.title, raw.description) is not None
        return not self.stored[key]


def collapse_duplicates(raw_jobs: list[RawJob]) -> list[RawJob]:
    """Keep the first posting of each key; hold back its copies while it has no stored row.

    A held-back copy stays unclaimed: the next scan sees it again, and the prefilter
    archives it against the row this scan stored. Storing it now would depend on the
    kept row surviving its own chunk. When the original is already stored, every copy
    goes through, since the prefilter archives each one for free.
    """
    seen = _SeenKeys()
    kept: list[RawJob] = []
    for raw in raw_jobs:
        key = posting_key(raw.company, raw.title, raw.description)
        if key is None or not seen.holds_back(raw, key):
            kept.append(raw)
    return kept
