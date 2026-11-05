"""Detects jobs whose source posting disappeared and archives them.

archive_stale_jobs marks them archived with closed_at set; format_archive_result words the outcome.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from peewee import fn

from moonlighter.core.db import Job
from moonlighter.discovery.sources.registry import build_http_scanners
from moonlighter.discovery.staleness import find_stale_jobs

ELIGIBLE_STATUSES = ("new", "reviewed", "applying", "needs_review")


class ArchiveStaleJobsError(ValueError):
    """Raised when job_id and company are both given (mutually exclusive filters)."""


@dataclass
class ArchiveResult:
    """Outcome of an archive_stale_jobs run."""

    archived: list[dict[str, str]] = field(default_factory=list)
    # Portal jobs archived because they aged past portal_max_age_days -- age is
    # the only closing signal a portal feed offers, so these are 'archived',
    # closed_at stays NULL: setting it would claim knowledge of the source we don't have.
    aged: list[dict[str, str]] = field(default_factory=list)
    max_age_days: int = 0
    failed_companies: list[str] = field(default_factory=list)
    # Jobs no listing can confirm (source='manual' and the like): the person
    # opens each link and says which closed. Never archived by age (Alberto's
    # rule, 2026-08-24).
    to_confirm: list[dict[str, Any]] = field(default_factory=list)


def _eligible_jobs_query(job_id: int | None, company: str | None) -> Any:
    query = Job.select().where(Job.status.in_(ELIGIBLE_STATUSES))
    if job_id is not None:
        query = query.where(Job.id == job_id)
    elif company is not None:
        query = query.where(fn.LOWER(Job.company) == company.lower())
    return query


def _group_by_source_company(jobs: list[Job]) -> dict[tuple[str, str], list[Job]]:
    groups: dict[tuple[str, str], list[Job]] = {}
    for job in jobs:
        groups.setdefault((job.source, job.company), []).append(job)
    return groups


def _summary(job: Job) -> dict[str, str]:
    return {"company": job.company, "title": job.title, "url": job.url}


def _archive_closed(jobs: list[Job], closed_at: datetime) -> list[dict[str, str]]:
    for job in jobs:
        job.status = "archived"
        job.closed_at = closed_at
        job.save()
    return [_summary(job) for job in jobs]


def _archive_aged(jobs: list[Job]) -> list[dict[str, str]]:
    for job in jobs:
        job.status = "archived"
        job.save()
    return [_summary(job) for job in jobs]


async def archive_stale_jobs(
    job_id: int | None, company: str | None, config: dict[str, Any]
) -> ArchiveResult:
    """Detects and archives eligible jobs that disappeared from their source.

    Archived means status='archived' with closed_at set. Mutually exclusive filters: job_id,
    company, or neither (all).
    """
    if job_id is not None and company is not None:
        raise ArchiveStaleJobsError("Provide job_id OR company, not both.")

    jobs = list(_eligible_jobs_query(job_id, company))
    jobs_by_company = _group_by_source_company(jobs)
    scanners = build_http_scanners()
    staleness = await find_stale_jobs(jobs_by_company, scanners, config)

    now = datetime.now()  # noqa: DTZ005 - the database stores naive local time
    return ArchiveResult(
        archived=_archive_closed(staleness.stale, now),
        aged=_archive_aged(staleness.stale_by_age),
        max_age_days=int(config.get("portal_max_age_days") or 0),
        failed_companies=staleness.failed_companies,
        to_confirm=[_to_confirm_entry(job, now) for job in staleness.unverifiable],
    )


def _to_confirm_entry(job: Job, now: datetime) -> dict[str, Any]:
    return {
        "id": job.id,
        "score": job.score,
        "status": job.status,
        "age_days": (now - job.found_at).days,
        "company": job.company,
        "title": job.title,
        "url": job.url,
    }


def _entry_line(entry: dict[str, str]) -> str:
    return f"  - {entry['company']} / {entry['title']} — {entry['url']}"


def _archived_lines(result: ArchiveResult) -> list[str]:
    if not result.archived:
        return ["No closed jobs found."]
    return [
        f"{len(result.archived)} job(s) archived (closed at source):",
        *map(_entry_line, result.archived),
    ]


def _aged_lines(result: ArchiveResult) -> list[str]:
    if not result.aged:
        return []
    return [
        (
            f"{len(result.aged)} portal job(s) archived by age "
            f"(older than {result.max_age_days} days; a portal feed cannot be re-checked):"
        ),
        *map(_entry_line, result.aged),
    ]


def _to_confirm_lines(result: ArchiveResult) -> list[str]:
    if not result.to_confirm:
        return []
    lines = [
        "",
        (
            f"{len(result.to_confirm)} job(s) have no listing to check against — "
            "open each link and say which are closed:"
        ),
    ]
    for entry in result.to_confirm:
        score = "—" if entry["score"] is None else f"{entry['score']:.1f}"
        age = "?" if entry["age_days"] is None else entry["age_days"]
        lines.append(
            f"  #{entry['id']} | {score} | {entry['status']} | {age}d | "
            f"{entry['company']} — {entry['title']}"
        )
        lines.append(f"    {entry['url']}")
    return lines


def _failed_lines(result: ArchiveResult) -> list[str]:
    if not result.failed_companies:
        return []
    return ["", f"⚠️  Could not check: {', '.join(result.failed_companies)}"]


def format_archive_result(result: ArchiveResult) -> str:
    if not (result.archived or result.aged or result.failed_companies or result.to_confirm):
        return "No closed jobs found."
    lines = [
        *_archived_lines(result),
        *_aged_lines(result),
        *_to_confirm_lines(result),
        *_failed_lines(result),
    ]
    return "\n".join(lines)
