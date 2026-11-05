"""Best-effort parsing of a free-text 'Who is hiring?' comment: company, title and workplace."""

from moonlighter.discovery.sources.base import remote_types_mentioned

_HEADER_LENGTH = 220
_MAXIMUM_SEGMENT_LENGTH = 60
_MINIMUM_HEADER_SEGMENTS = 3
_MAXIMUM_TITLE_LENGTH = 80


def parse_workplace(text: str) -> tuple[str | None, str | None]:
    """(remote_type, location) from the pipe-separated header of a posting.

    Convention: `Company | Role | City | ONSITE | Full-time`. Only short
    segments of the first ~220 characters count (anything longer is prose,
    and 'remote' in prose says nothing about the posting), and a header that
    states two different kinds ('ONSITE or REMOTE', 'ONSITE | Remote (US)')
    stays unknown. Location is set only for a remote segment, whose text
    ('Remote (Worldwide)') is eligibility information; for onsite/hybrid the
    city sits in another segment we cannot identify, and a wrong place there
    would turn into a deterministic archive.
    """
    segments = [segment.strip() for segment in text[:_HEADER_LENGTH].split("|")]
    if len(segments) < _MINIMUM_HEADER_SEGMENTS:
        return None, None
    stated = [
        (segment, remote_types_mentioned(segment))
        for segment in segments[1:]
        if len(segment) <= _MAXIMUM_SEGMENT_LENGTH
    ]
    kinds = set().union(*(segment_kinds for _, segment_kinds in stated))
    if len(kinds) != 1:
        return None, None
    (kind,) = kinds
    location = (
        next(segment for segment, segment_kinds in stated if segment_kinds)
        if kind == "remote"
        else None
    )
    return kind, location


def _cap(text: str) -> str:
    return (text[:_MAXIMUM_TITLE_LENGTH] + "…") if len(text) > _MAXIMUM_TITLE_LENGTH else text


def parse_title(first_line: str, full_text: str) -> tuple[str, str]:
    """(company, title) from a posting's first line, or a fallback that keeps the job."""
    # HN comments render paragraphs as <p>, which the tag-strip in
    # _fetch_comment turns into a space, not a newline -- so "first_line"
    # is really "the whole flattened comment" and `rest` after the first
    # separator is unbounded (a real ~1200-char title was observed live).
    # Cap it the same way as the no-separator fallback below.
    for separator in ("|", "-"):
        if separator in first_line:
            company, _, rest = first_line.partition(separator)
            company = company.strip()
            if company:
                return company, _cap(rest.strip() or first_line.strip())
    return "HN Who's Hiring", _cap(full_text) or "Untitled posting"
