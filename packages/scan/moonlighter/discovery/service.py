"""Scan service: discovers jobs (HTTP + LinkedIn), evaluates with the LLM, and saves.

The MCP tools in server.py are thin wrappers that call these functions passing
config/profile/caller. The logic lives here, testable in isolation.
"""

import asyncio
import json
import re
from dataclasses import replace
from datetime import datetime
from typing import Any

import httpx
from moonlighter.core.config import load_company_list
from moonlighter.core.db import Job, ScanLog
from moonlighter.core.llm import LLMCaller, is_spend_limit
from moonlighter.core.log import get_logger
from moonlighter.core.metrics import record_spend_limit_hit
from moonlighter.core.plugins import discover_entry_points
from moonlighter.discovery.archive import _format_archive_result
from moonlighter.discovery.archive import archive_stale_jobs as archive_stale_jobs
from moonlighter.discovery.evaluator import (
    EvalInput,
    evaluate_job,
    evaluate_jobs_batch,
    should_skip_by_title,
)
from moonlighter.discovery.posting import fetch_posting_via_ats
from moonlighter.discovery.sources.base import RawJob, ScanStats
from moonlighter.discovery.sources.registry import build_http_scanners
from moonlighter.discovery.urls import normalize_job_url
from moonlighter.views import render_jobs_table
from peewee import IntegrityError

logger = get_logger(__name__)


class _StopScan:
    """Sentinel returned by a coroutine that detected a spend limit and stopped."""


def _model_for(config: dict[str, Any]) -> str:
    model: str = config.get("eval_model", config.get("llm_model", "claude-haiku-4-5-20251001"))
    return model


def _claim(raw: RawJob) -> bool:
    """Reserves the URL in ScanLog before any work. ScanLog.create is synchronous,
    so asyncio doesn't switch context between the insert and the return — the
    UNIQUE constraint on job_url is the atomic guard against two concurrent calls
    evaluating the same URL. Returns False when the URL was already reserved."""
    try:
        ScanLog.create(job_url=raw.url, source=raw.source)
        return True
    except IntegrityError:
        return False


def _release(raw: RawJob) -> None:
    """Releases the claim for a retry in a future scan (never leaves an orphaned claim)."""
    ScanLog.delete().where(ScanLog.job_url == raw.url).execute()


def _create_job(
    source: str,
    company: str,
    title: str,
    url: str,
    location: str | None,
    remote_type: str | None,
    description: str | None,
    posted_at: datetime | None,
    **scoring: Any,
) -> Job | None:
    """Create a Job (shared core of _persist/_persist_manual). None if the URL already exists."""
    try:
        job: Job = Job.create(
            source=source,
            company=company,
            title=title,
            url=url,
            location=location,
            remote_type=remote_type,
            description=description,
            posted_at=posted_at,
            **scoring,
        )
        return job
    except IntegrityError:
        return None


def _persist(raw: RawJob, **scoring: Any) -> Job | None:
    """Saves the RawJob as a Job with the scoring fields. None if the URL already exists."""
    return _create_job(
        raw.source,
        raw.company,
        raw.title,
        raw.url,
        raw.location,
        raw.remote_type,
        raw.description,
        raw.posted_at,
        **scoring,
    )


async def _run_browser_scanner(
    scanner_cls: type[Any], keywords: str, config: dict[str, Any]
) -> tuple[list[RawJob], str | None]:
    """Runs one browser-based scanner plugin (requires prior login, same shape as
    LinkedInScanner). An expired session becomes a warning; any other failure —
    including no browser being available — is silent so it doesn't block the
    HTTP results."""
    from moonlighter.discovery.sources.base import ScannerSessionExpiredError

    try:
        from moonlighter.core import browser

        page = await browser.new_page(config)
    except Exception:
        return [], None
    try:
        jobs = await scanner_cls(page).scan(keywords=keywords)
        return jobs, None
    except ScannerSessionExpiredError as e:
        label = scanner_cls.__name__.removesuffix("Scanner")
        return [], f"⚠️  {label}: {e}"
    except Exception:
        return [], None
    finally:
        await page.close()


async def _collect_raw_jobs(
    keywords: str, config: dict[str, Any], companies: dict[str, list[str]]
) -> tuple[list[RawJob], str | None]:
    """Collects jobs from the HTTP sources and every registered browser-scanner
    plugin (e.g. LinkedIn, if installed). Returns the raw jobs and any warnings
    -- from the browser scanners plus one line per HTTP/portal source that
    errored or came back empty -- joined into one string."""
    scanners = build_http_scanners()

    warnings: list[str] = []
    for unknown in sorted(set(companies) - set(scanners)):
        warnings.append(
            f"⚠️  company_list.yaml: unknown source {unknown!r} — no scanner with that name, "
            "entries ignored"
        )

    stats: ScanStats = {}
    raw_jobs: list[RawJob] = []
    for source, scanner in scanners.items():
        slugs = companies.get(source, [])
        if slugs:
            raw_jobs.extend(await scanner.scan(slugs, stats=stats))

    for scanner_cls in discover_entry_points("moonlighter.scanners"):
        jobs, warning = await _run_browser_scanner(scanner_cls, keywords, config)
        raw_jobs.extend(jobs)
        if warning:
            warnings.append(warning)

    raw_jobs.extend(await _scan_gupy(keywords, config, stats))
    raw_jobs.extend(await _scan_remoteok(config, stats, keywords))
    raw_jobs.extend(await _scan_remotive(config, stats, keywords))
    raw_jobs.extend(await _scan_wwr(config, stats, keywords))
    raw_jobs.extend(await _scan_hn_whoishiring(config, stats, keywords))
    warnings.extend(_stats_warnings(stats))
    raw_jobs = [replace(j, url=normalize_job_url(j.url)) for j in raw_jobs]
    return raw_jobs, ("\n".join(warnings) or None)


async def _scan_gupy(keywords: str, config: dict[str, Any], stats: ScanStats) -> list[RawJob]:
    """Gupy is a portal-wide keyword feed (all companies hosted on Gupy, not a
    per-company board), so it's dispatched here like LinkedIn rather than through
    the SOURCES registry -- and gated hard behind a config flag (default off)
    since an ungated run returns all-BR jobs that would flood the pipeline."""
    if not config.get("scan_gupy"):
        return []
    from moonlighter.discovery.sources.http import GupyScanner

    return await GupyScanner().scan(keywords=keywords or "software engineer", stats=stats)


def _matches_keywords(title: str, keywords: str) -> bool:
    """Comma-separated terms; a title matches when ANY term is a
    case-insensitive substring. No keywords = everything matches."""
    terms = [t.strip().lower() for t in keywords.split(",") if t.strip()]
    if not terms:
        return True
    lowered = title.lower()
    return any(term in lowered for term in terms)


async def _scan_remoteok(config: dict[str, Any], stats: ScanStats, keywords: str) -> list[RawJob]:
    """RemoteOK is a portal-wide remote-jobs board, dispatched like Gupy --
    config-gated (off by default) to avoid flooding scans without the
    operator opting in. The feed has no server-side query, so it is filtered
    by title keywords here before any LLM evaluation."""
    if not config.get("scan_remoteok"):
        return []
    from moonlighter.discovery.sources.http import RemoteOKScanner

    jobs = await RemoteOKScanner().scan(stats=stats)
    return [j for j in jobs if _matches_keywords(j.title, keywords)]


async def _scan_remotive(config: dict[str, Any], stats: ScanStats, keywords: str) -> list[RawJob]:
    """Remotive is a portal-wide remote-jobs board, dispatched like Gupy --
    config-gated (off by default). ToS caps usage at 4 requests/day -- no
    rate-limiter here, the operator is responsible for scan frequency. The
    feed has no server-side query, so it is filtered by title keywords here
    before any LLM evaluation."""
    if not config.get("scan_remotive"):
        return []
    from moonlighter.discovery.sources.http import RemotiveScanner

    jobs = await RemotiveScanner().scan(stats=stats)
    return [j for j in jobs if _matches_keywords(j.title, keywords)]


async def _scan_wwr(config: dict[str, Any], stats: ScanStats, keywords: str) -> list[RawJob]:
    """WeWorkRemotely is a portal-wide RSS feed, dispatched like Gupy --
    config-gated (off by default). The feed has no server-side query, so it
    is filtered by title keywords here before any LLM evaluation."""
    if not config.get("scan_wwr"):
        return []
    from moonlighter.discovery.sources.http import WeWorkRemotelyScanner

    jobs = await WeWorkRemotelyScanner().scan(stats=stats)
    return [j for j in jobs if _matches_keywords(j.title, keywords)]


async def _scan_hn_whoishiring(
    config: dict[str, Any], stats: ScanStats, keywords: str
) -> list[RawJob]:
    """HN's monthly Who is hiring? thread, dispatched like Gupy -- config-gated
    (off by default). Weakest signal of the 4 new boards (free-text comments,
    not structured fields) -- see HNWhoIsHiringScanner's docstring. The feed
    has no server-side query, so it is filtered by title keywords here before
    any LLM evaluation."""
    if not config.get("scan_hn_whoishiring"):
        return []
    from moonlighter.discovery.sources.http import HNWhoIsHiringScanner

    jobs = await HNWhoIsHiringScanner().scan(stats=stats)
    return [j for j in jobs if _matches_keywords(j.title, keywords)]


def _drop_already_seen(raw_jobs: list[RawJob]) -> list[RawJob]:
    seen = {normalize_job_url(row.job_url) for row in ScanLog.select(ScanLog.job_url)}
    return [j for j in raw_jobs if normalize_job_url(j.url) not in seen]


async def _evaluate_and_store(
    new_jobs: list[RawJob], config: dict[str, Any], profile: dict[str, Any], caller: LLMCaller
) -> tuple[list[Job], bool]:
    """Evaluates and saves jobs in concurrent BATCHES (up to scan_concurrency batches
    in parallel, scan_batch_size jobs per batch), stopping at the first spend limit
    or unexpected error. Returns the saved jobs and whether it stopped."""
    threshold = config["score_threshold"]
    model = _model_for(config)
    blocklist: list[str] = config.get("title_blocklist", [])
    concurrency: int = config.get("scan_concurrency", 5)
    batch_size: int = config.get("scan_batch_size", 5)
    stop = asyncio.Event()
    semaphore = asyncio.Semaphore(concurrency)

    async def evaluate_chunk(chunk: list[RawJob]) -> list[Job | _StopScan]:
        async with semaphore:
            # Already stopped while waiting for the permit: don't reserve or call the LLM.
            if stop.is_set():
                return [_StopScan()]

            results: list[Job | _StopScan] = []
            to_eval: list[RawJob] = []
            for raw in chunk:
                if not _claim(raw):
                    continue  # already reserved (race/previous scan)
                matched = should_skip_by_title(raw.title, blocklist)
                if matched:
                    job = _persist(
                        raw,
                        score=0.0,
                        score_notes=f"title filtered: {matched!r}",
                        caveats="[]",
                        status="archived",
                    )
                    if job is not None:
                        results.append(job)
                else:
                    to_eval.append(raw)

            if not to_eval:
                return results

            try:
                evals = await evaluate_jobs_batch(
                    [
                        EvalInput(r.company, r.title, r.description or f"{r.title} at {r.company}")
                        for r in to_eval
                    ],
                    profile,
                    model,
                    caller,
                )
            except Exception as e:
                for raw in to_eval:
                    _release(raw)
                if is_spend_limit(e):
                    record_spend_limit_hit()
                    stop.set()
                    results.append(_StopScan())
                    return results
                logger.error("scan: unexpected error in batch — %s", e)
                # Returns results (title-filtered jobs already persisted in this chunk)
                # instead of propagating — the raw exception would make gather() discard
                # the whole chunk from the report, undercounting jobs already saved in the DB.
                results.append(_StopScan())
                return results

            for raw, result in zip(to_eval, evals, strict=True):
                job = _persist(
                    raw,
                    score=result.score,
                    score_notes=result.score_notes,
                    caveats=json.dumps(result.caveats),
                    salary_min=result.salary_min,
                    salary_max=result.salary_max,
                    salary_currency=result.salary_currency,
                    salary_source=result.salary_source,
                    status="new" if result.score >= threshold else "archived",
                )
                if job is not None:
                    results.append(job)
            return results

    chunks = [new_jobs[i : i + batch_size] for i in range(0, len(new_jobs), batch_size)]
    chunk_outcomes = await asyncio.gather(*map(evaluate_chunk, chunks), return_exceptions=True)

    saved: list[Job] = []
    spend_hit = False
    for outcome in chunk_outcomes:
        if isinstance(outcome, BaseException):
            logger.error("scan: batch failed — %s", outcome)
            spend_hit = True
            continue
        for item in outcome:
            if isinstance(item, _StopScan):
                spend_hit = True
            else:
                saved.append(item)

    if spend_hit:
        logger.warning("scan_and_evaluate: stopped by spend limit after %d jobs", len(saved))
    return saved, spend_hit


def _stats_warnings(stats: ScanStats) -> list[str]:
    """One report line per source that errored or came back empty. Zero-from-N
    with no errors still earns a line: it is exactly the shape the dead Ashby
    GraphQL API produced for weeks (HTTP 200, error payload, zero jobs). A
    healthy source adds nothing."""
    lines: list[str] = []
    for source, s in sorted(stats.items()):
        if s.errors == 0 and s.jobs > 0:
            continue
        scope = f" from {s.companies} companies" if s.companies else ""
        errs = f" ({s.errors} fetch errors)" if s.errors else ""
        lines.append(f"⚠️  {source}: {s.jobs} jobs{scope}{errs}")
    return lines


def _with_warning(message: str, warning: str | None) -> str:
    return f"{message}\n\n{warning}" if warning else message


def _format_report(saved: list[Job], spend_hit: bool, threshold: float) -> str:
    above = [j for j in saved if j.status == "new"]
    title_filtered = sum(
        1 for j in saved if j.score_notes and j.score_notes.startswith("title filtered:")
    )
    below = len(saved) - len(above) - title_filtered
    spend_note = (
        "\n\n⚠️  Spend limit reached — scan stopped (remaining jobs are left for the next scan)."
        if spend_hit
        else ""
    )

    if not above:
        return (
            f"{len(saved)} jobs processed. None passed the threshold of {threshold}. "
            f"({title_filtered} filtered by title, {below} below score){spend_note}"
        )

    table = render_jobs_table(above)
    footer = (
        f"\n∗ = salary estimated by the LLM  |  "
        f"{below} below threshold  |  {title_filtered} filtered by title"
    )
    return (
        f"{len(saved)} jobs processed. {len(above)} above threshold:\n\n{table}{footer}{spend_note}"
    )


async def scan_and_evaluate(
    keywords: str, phase: str, config: dict[str, Any], profile: dict[str, Any], caller: LLMCaller
) -> str:
    companies = load_company_list(phase=None if phase == "all" else phase)
    raw_jobs, li_warning = await _collect_raw_jobs(keywords, config, companies)
    new_jobs = _drop_already_seen(raw_jobs)

    if new_jobs:
        saved, spend_hit = await _evaluate_and_store(new_jobs, config, profile, caller)
        report = _format_report(saved, spend_hit, config["score_threshold"])
    else:
        report = "No new jobs found."

    archive_result = await archive_stale_jobs(None, None, config)
    report = f"{report}\n\n{_format_archive_result(archive_result)}"

    return _with_warning(report, li_warning)


async def scan_company(
    source: str, company: str, config: dict[str, Any], profile: dict[str, Any], caller: LLMCaller
) -> str:
    """Scan every open posting at ONE company right now, without touching
    company_list.yaml. `company` is an ATS slug, or (Recruitee) a custom
    career domain."""
    scanners = build_http_scanners()
    if source not in scanners:
        return (
            f"Unknown source {source!r}. Valid sources: {', '.join(sorted(scanners))}. "
            "Portal boards (gupy, remoteok, remotive, weworkremotely, hn_whoishiring) "
            "are enabled via config flags and scanned by scan_and_evaluate."
        )
    stats: ScanStats = {}
    raw_jobs = await scanners[source].scan([company], stats=stats)
    raw_jobs = [replace(j, url=normalize_job_url(j.url)) for j in raw_jobs]
    new_jobs = _drop_already_seen(raw_jobs)

    if new_jobs:
        saved, spend_hit = await _evaluate_and_store(new_jobs, config, profile, caller)
        report = _format_report(saved, spend_hit, config["score_threshold"])
    else:
        report = f"No new jobs at {company!r} ({len(raw_jobs)} found, all already known)."

    report += (
        f"\n\nTip: add {company!r} under '{source}:' in company_list.yaml "
        "to include it in recurring scans."
    )
    return _with_warning(report, "\n".join(_stats_warnings(stats)) or None)


async def add_job(
    url: str,
    company: str,
    title: str,
    description: str,
    config: dict[str, Any],
    profile: dict[str, Any],
    caller: LLMCaller,
) -> str:
    url = normalize_job_url(url)
    if not description or not company or not title:
        posting = await fetch_posting_via_ats(url)
        if posting is not None:
            company = company or posting.company or ""
            title = title or posting.title or ""
            description = description or posting.description or ""
    if not description:
        fetched, error = await _fetch_description(url)
        if error:
            return error
        description = fetched or ""
    if not company or not title:
        return "Provide at least 'company' and 'title' along with the URL."

    already = _existing_job_message(url)
    if already:
        return already

    matched = should_skip_by_title(title, config.get("title_blocklist", []))
    if matched:
        _persist_manual(
            company,
            title,
            url,
            description,
            score=0.0,
            score_notes=f"title filtered: {matched!r}",
            caveats="[]",
            status="archived",
        )
        return f"Job discarded by the title filter (pattern: {matched!r})."

    threshold = config["score_threshold"]
    result = await evaluate_job(
        company=company,
        title=title,
        description=description,
        profile=profile,
        model=_model_for(config),
        _caller=caller,
    )
    status = "new" if result.score >= threshold else "archived"
    job = _persist_manual(
        company,
        title,
        url,
        description,
        score=result.score,
        score_notes=result.score_notes,
        caveats=json.dumps(result.caveats),
        salary_min=result.salary_min,
        salary_max=result.salary_max,
        salary_currency=result.salary_currency,
        salary_source=result.salary_source,
        status=status,
    )
    if job is None:
        return "Job already in the database (URL conflict)."
    return _format_add_result(job, company, title, result, threshold, status)


async def _fetch_description(url: str) -> tuple[str | None, str | None]:
    """Fetches and cleans (strips HTML from) the job description. Returns (description,
    error) — only one of the two is non-null. Doesn't work on pages that require login."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "moonlighter/0.1"})
        if r.status_code != 200:
            return None, (
                f"Could not fetch the URL (HTTP {r.status_code}). Provide 'description' manually."
            )
        # Remove script/style/noscript WITH their contents first: a bare
        # tag-strip leaves e.g. a styled-components CSS bundle as the
        # "description" of any SPA page (job #2646, the Ziflow case).
        text = re.sub(r"(?is)<(script|style|noscript)\b[^>]*>.*?</\1\s*>", " ", r.text)
        text = re.sub(r"<[^>]+>", " ", text).strip()
        return re.sub(r"\s+", " ", text)[:8000], None
    except Exception as e:
        return None, (
            f"Error fetching URL: {e}\n"
            f"For pages that require login (LinkedIn, etc.), provide "
            f"'company', 'title', and 'description' manually."
        )


def _existing_job_message(url: str) -> str | None:
    """'Already exists' message if the URL is already in the DB; None otherwise."""
    if not ScanLog.select().where(ScanLog.job_url == url).exists():
        return None
    try:
        job = Job.get(Job.url == url)
    except Job.DoesNotExist:
        return None
    return f"Job already in the database (id={job.id}, score={job.score:.1f}, status={job.status})."


def _persist_manual(
    company: str, title: str, url: str, description: str, **scoring: Any
) -> Job | None:
    """Saves a manual job (source='manual') + the claim in ScanLog. None if the URL
    already exists (race/conflict)."""
    job = _create_job("manual", company, title, url, None, None, description, None, **scoring)
    if job is not None:
        try:
            ScanLog.create(job_url=url, source="manual")
        except IntegrityError:
            return None
    return job


def _format_add_result(
    job: Job, company: str, title: str, result: Any, threshold: float, status: str
) -> str:
    icon = "✓ NEW" if status == "new" else "archived"
    caveats_str = "\n".join(f"  ⚠ {c}" for c in result.caveats) if result.caveats else "  none"
    return (
        f"{icon} — {company} / {title}\n"
        f"Score: {result.score:.1f}/10  (threshold: {threshold})\n"
        f"Notes: {result.score_notes}\n"
        f"Caveats:\n{caveats_str}\n"
        f"id={job.id}"
    )
