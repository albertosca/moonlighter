"""The portal-wide feeds: Gupy, RemoteOK, Remotive, WeWorkRemotely and HN Who is hiring.

Each is config-gated (off by default) and filtered by title keywords before any
LLM evaluation, because the feeds have no server-side query.
"""

from typing import Any

from moonlighter.discovery.sources.base import RawJob, ScanStats
from moonlighter.discovery.sources.job_feeds.gupy import GupyScanner
from moonlighter.discovery.sources.job_feeds.hacker_news import HNWhoIsHiringScanner
from moonlighter.discovery.sources.job_feeds.remoteok import RemoteOKScanner
from moonlighter.discovery.sources.job_feeds.remotive import RemotiveScanner
from moonlighter.discovery.sources.job_feeds.weworkremotely import WeWorkRemotelyScanner


def _matches_keywords(title: str, keywords: str) -> bool:
    """Comma-separated terms; a title matches when ANY term is a case-insensitive substring.

    No keywords means everything matches.
    """
    terms = [term.strip().lower() for term in keywords.split(",") if term.strip()]
    if not terms:
        return True
    lowered = title.lower()
    return any(term in lowered for term in terms)


async def _scan_gupy(config: dict[str, Any], stats: ScanStats, keywords: str) -> list[RawJob]:
    """Gupy is a portal-wide keyword feed (all companies hosted on Gupy, not a per-company board).

    It is dispatched here like LinkedIn rather than through the SOURCES registry,
    and gated hard behind a config flag (default off) since an ungated run
    returns all-BR jobs that would flood the pipeline.
    """
    if not config.get("scan_gupy") or not keywords.strip():
        return []
    return await GupyScanner().scan(keywords=keywords, stats=stats)


async def _scan_remoteok(config: dict[str, Any], stats: ScanStats, keywords: str) -> list[RawJob]:
    """RemoteOK is a portal-wide remote-jobs board, dispatched like Gupy.

    Config-gated (off by default) to avoid flooding scans without the operator
    opting in, and filtered by title keywords before any LLM evaluation.
    """
    if not config.get("scan_remoteok"):
        return []
    jobs = await RemoteOKScanner().scan(stats=stats)
    return [job for job in jobs if _matches_keywords(job.title, keywords)]


async def _scan_remotive(config: dict[str, Any], stats: ScanStats, keywords: str) -> list[RawJob]:
    """Remotive is a portal-wide remote-jobs board, dispatched like Gupy.

    Config-gated (off by default). ToS caps usage at 4 requests/day -- no
    rate-limiter here, the operator is responsible for scan frequency.
    """
    if not config.get("scan_remotive"):
        return []
    jobs = await RemotiveScanner().scan(category=config.get("remotive_category"), stats=stats)
    return [job for job in jobs if _matches_keywords(job.title, keywords)]


async def _scan_wwr(config: dict[str, Any], stats: ScanStats, keywords: str) -> list[RawJob]:
    """WeWorkRemotely is a portal-wide RSS feed, dispatched like Gupy, config-gated (off by default)."""
    if not config.get("scan_wwr"):
        return []
    jobs = await WeWorkRemotelyScanner().scan(category=config.get("wwr_category"), stats=stats)
    return [job for job in jobs if _matches_keywords(job.title, keywords)]


async def _scan_hn_whoishiring(
    config: dict[str, Any], stats: ScanStats, keywords: str
) -> list[RawJob]:
    """HN's monthly Who is hiring? thread, dispatched like Gupy, config-gated (off by default).

    Weakest signal of the boards (free-text comments, not structured fields) --
    see HNWhoIsHiringScanner's docstring.
    """
    if not config.get("scan_hn_whoishiring"):
        return []
    jobs = await HNWhoIsHiringScanner().scan(stats=stats)
    return [job for job in jobs if _matches_keywords(job.title, keywords)]


async def scan_portals(config: dict[str, Any], stats: ScanStats, keywords: str) -> list[RawJob]:
    """The jobs of every enabled portal feed, in a fixed order, one feed at a time."""
    raw_jobs: list[RawJob] = []
    raw_jobs.extend(await _scan_gupy(config, stats, keywords))
    raw_jobs.extend(await _scan_remoteok(config, stats, keywords))
    raw_jobs.extend(await _scan_remotive(config, stats, keywords))
    raw_jobs.extend(await _scan_wwr(config, stats, keywords))
    raw_jobs.extend(await _scan_hn_whoishiring(config, stats, keywords))
    return raw_jobs
