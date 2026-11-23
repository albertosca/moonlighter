"""Checks a job added by URL against the board of the ATS its URL belongs to.

A manual job has no listing of its own, but a URL pasted from a supported board
(Greenhouse, Ashby) names the board's slug and the posting's id. The job is then
open exactly when that id is among the board's open postings. The comparison is
by id because the listing's URL is not the pasted one: Greenhouse's absolute_url
can be the company's own careers page (?gh_jid=<id>), and boards. and job-boards.
serve the same posting.
"""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from moonlighter.core.db import Job
from moonlighter.discovery.sources.base import RawJob

# Only the US hosts: the Greenhouse scanner reads boards-api.greenhouse.io, which
# cannot see a job-boards.eu.greenhouse.io board, so an EU job stays with the person.
_BOARD_URLS = {
    "greenhouse": re.compile(
        r"^https?://(?:job-)?boards\.greenhouse\.io/(?P<slug>[^/?#]+)/jobs/(?P<posting>\d+)"
    ),
    "ashby": re.compile(
        r"^https?://jobs\.ashbyhq\.com/(?P<slug>[^/?#]+)/(?P<posting>[0-9a-f-]{36})"
    ),
}
_LISTED_IDS = {
    "greenhouse": re.compile(r"(?:/jobs/|[?&]gh_jid=)(?P<posting>\d+)"),
    "ashby": re.compile(r"/(?P<posting>[0-9a-f-]{36})(?:[/?#]|$)"),
}

ListingFetcher = Callable[[str, str, str], Awaitable[list[RawJob] | None]]


@dataclass
class ManualCheck:
    stale: list[Job] = field(default_factory=list)
    unverifiable: list[Job] = field(default_factory=list)
    failed_companies: list[str] = field(default_factory=list)


def board_posting(url: str) -> tuple[str, str, str] | None:
    """(source, slug, posting id) of a supported board URL, or None."""
    for source, pattern in _BOARD_URLS.items():
        if match := pattern.match(url):
            return source, match["slug"], match["posting"]
    return None


def _listed_ids(source: str, listing: list[RawJob]) -> set[str] | None:
    """Every open posting's id, or None when one of them has no readable id."""
    ids = set()
    for raw in listing:
        match = _LISTED_IDS[source].search(raw.url)
        if match is None:
            return None
        ids.add(match["posting"])
    return ids


async def check_manual_jobs(jobs: list[Job], fetch_listing: ListingFetcher) -> ManualCheck:
    """Splits manual jobs into stale, left to the person, and boards that could not be read.

    fetch_listing(source, slug, company) returns the board's open postings, or None
    after it has recorded the failure itself.
    """
    check = ManualCheck()
    by_board: dict[tuple[str, str], list[tuple[Job, str]]] = {}
    for job in jobs:
        posting = board_posting(job.url)
        if posting is None:
            check.unverifiable.append(job)
            continue
        source, slug, posting_id = posting
        by_board.setdefault((source, slug), []).append((job, posting_id))
    for (source, slug), pairs in by_board.items():
        company = pairs[0][0].company
        listing = await fetch_listing(source, slug, company)
        if listing is None:
            continue
        open_ids = _listed_ids(source, listing)
        if open_ids is None:
            check.failed_companies.append(company)
            continue
        check.stale.extend(job for job, posting_id in pairs if posting_id not in open_ids)
    return check
