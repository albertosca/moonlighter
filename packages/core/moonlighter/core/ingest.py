"""URL → persisted Job, with no LLM anywhere: the bridge that lets
`moonlighter-apply prepare --url` work without the scan slice installed.

Mirrors what add_job does before it evaluates, minus the evaluation: the
posting is read through its ATS API when the URL has a known shape, the
generic page fetch fills a missing description, and the row is stored
unscored (needs_review) so verify_job can score it later. Registered in
ScanLog under source 'manual', the way add_job does, so a later scan does
not offer it again as new.
"""

import datetime

from moonlighter.core.db import Job, ScanLog
from moonlighter.core.posting import fetch_description, fetch_posting_via_ats
from moonlighter.core.urls import normalize_job_url


async def job_from_url(url: str) -> Job | None:
    """The Job for `url`: the existing row when there is one, else a new
    unscored row read from the posting. None when the posting cannot be read
    well enough to name it (no company or title) or the fetch fails."""
    url = normalize_job_url(url)
    existing = Job.get_or_none(Job.url == url)
    if existing is not None:
        return existing
    posting = await fetch_posting_via_ats(url)
    company = (posting.company if posting else None) or ""
    title = (posting.title if posting else None) or ""
    description = (posting.description if posting else None) or ""
    if not description:
        fetched, error = await fetch_description(url)
        if error:
            return None
        description = fetched or ""
    if not company or not title:
        return None
    job = Job.create(
        source="manual",
        company=company,
        title=title,
        url=url,
        description=description,
        score=None,
        score_notes="ingested by URL for a sheet — not evaluated",
        caveats="[]",
        status="needs_review",
        found_at=datetime.datetime.now(),
    )
    ScanLog.get_or_create(job_url=url, defaults={"source": "manual"})
    return job
