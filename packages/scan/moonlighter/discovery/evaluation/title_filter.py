"""The free pre-filter that drops postings by title before any LLM call."""


def should_skip_by_title(title: str, blocklist: list[str]) -> str | None:
    """Returns the pattern that matched if the title should be discarded, or None.

    Case-insensitive substring matching. Zero cost — no LLM.
    """
    lower = title.lower()
    for pattern in blocklist:
        if pattern.lower() in lower:
            return pattern
    return None
