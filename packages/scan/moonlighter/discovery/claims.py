"""The URL claim that keeps two concurrent scans from evaluating the same job."""

from peewee import IntegrityError

from moonlighter.core.db import ScanLog
from moonlighter.core.urls import normalize_job_url
from moonlighter.discovery.sources.base import RawJob


def claim(raw: RawJob) -> bool:
    """Reserve the raw job's URL in ScanLog before any work (see `claim_url`)."""
    return claim_url(raw.url, raw.source)


def claim_url(url: str, source: str) -> bool:
    """Reserve the URL in ScanLog before any work.

    ScanLog.create is synchronous, so asyncio doesn't switch context between the
    insert and the return: the UNIQUE constraint on job_url is the atomic guard
    against two concurrent calls evaluating the same URL. Returns False when the
    URL was already reserved.
    """
    try:
        ScanLog.create(job_url=url, source=source)
    except IntegrityError:
        return False
    return True


def release(raw: RawJob) -> None:
    """Release the claim for a retry in a future scan (never leaves an orphaned claim)."""
    ScanLog.delete().where(ScanLog.job_url == raw.url).execute()


def drop_already_seen(raw_jobs: list[RawJob]) -> list[RawJob]:
    """The raw jobs whose normalised URL no earlier scan has claimed."""
    seen = {normalize_job_url(row.job_url) for row in ScanLog.select(ScanLog.job_url)}
    return [raw_job for raw_job in raw_jobs if normalize_job_url(raw_job.url) not in seen]
