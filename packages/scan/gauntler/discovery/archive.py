"""archive_stale_jobs: detects jobs whose source posting disappeared and marks
them closed. Extracted from discovery/service.py (pure move, no behavior
change)."""

import datetime
from dataclasses import dataclass, field
from typing import Any

from gauntler.core.db import Job
from gauntler.discovery.sources.registry import build_http_scanners
from gauntler.discovery.staleness import find_stale_jobs
from peewee import fn

ELIGIBLE_STATUSES = ("new", "reviewed", "applying", "needs_review")


class ArchiveStaleJobsError(ValueError):
    """Raised when job_id and company are both given (mutually exclusive filters)."""


@dataclass
class ArchiveResult:
    """Outcome of an archive_stale_jobs run."""

    archived: list[dict[str, str]] = field(default_factory=list)
    failed_companies: list[str] = field(default_factory=list)


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


async def archive_stale_jobs(
    job_id: int | None, company: str | None, config: dict[str, Any]
) -> ArchiveResult:
    """Detects and archives (status='closed') eligible jobs that disappeared from
    their source. Mutually exclusive filters: job_id, company, or neither (all)."""
    if job_id is not None and company is not None:
        raise ArchiveStaleJobsError("Provide job_id OR company, not both.")

    jobs = list(_eligible_jobs_query(job_id, company))
    jobs_by_company = _group_by_source_company(jobs)
    scanners = build_http_scanners()
    staleness = await find_stale_jobs(jobs_by_company, scanners, config)

    now = datetime.datetime.now()
    archived: list[dict[str, str]] = []
    for job in staleness.stale:
        job.status = "closed"
        job.closed_at = now
        job.save()
        archived.append({"company": job.company, "title": job.title, "url": job.url})

    return ArchiveResult(archived=archived, failed_companies=staleness.failed_companies)


def _format_archive_result(result: ArchiveResult) -> str:
    if not result.archived and not result.failed_companies:
        return "Nenhuma vaga fechada encontrada."
    lines: list[str] = []
    if result.archived:
        lines.append(f"{len(result.archived)} vaga(s) arquivada(s) (fechada na fonte):")
        lines.extend(f"  - {j['company']} / {j['title']} — {j['url']}" for j in result.archived)
    else:
        lines.append("Nenhuma vaga fechada encontrada.")
    if result.failed_companies:
        lines.append("")
        lines.append(f"⚠️  Não foi possível checar: {', '.join(result.failed_companies)}")
    return "\n".join(lines)
