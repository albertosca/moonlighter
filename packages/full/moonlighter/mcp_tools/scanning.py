"""MCP tools that find jobs: scan the boards, scan one company, add or verify one by hand."""

from typing import Any

from mcp.server.mcpserver import Context

from moonlighter._tool_logging import tool_logged
from moonlighter.app_context import AppContext, refreshed_app_context
from moonlighter.core.metrics import operation_metrics
from moonlighter.discovery import archive, manual_jobs
from moonlighter.discovery import scanning as discovery_scanning
from moonlighter.discovery.archive import ArchiveStaleJobsError, format_archive_result
from moonlighter.discovery.results import render_scan_report


@tool_logged
async def scan_and_evaluate(  # noqa: D417 - context is injected by FastMCP; the docstring is the served description
    keywords: str = "", phase: str = "phase1", *, context: Context[AppContext, Any]
) -> str:
    """Scan job boards, evaluate with LLM, return new jobs above threshold.

    By default scans only phase 1 (priority BR companies) to save tokens.
    Use phase='phase2', 'phase3', or 'all' to explicitly scan more companies.

    Args:
        keywords: keywords for the LinkedIn scanner (optional)
        phase: "phase1" (default/BR), "phase2" (remote-first global),
               "phase3" (big techs), or "all" (everything)
    """
    app_context = refreshed_app_context(context)
    with operation_metrics("scan_and_evaluate"):
        return render_scan_report(
            await discovery_scanning.scan_and_evaluate(
                keywords,
                phase,
                app_context.config,
                app_context.profile,
                app_context.llm_caller,
            )
        )


@tool_logged
async def scan_company(  # noqa: D417 - context is injected by FastMCP; the docstring is the served description
    source: str, company: str, *, context: Context[AppContext, Any]
) -> str:
    """Scan every open posting at ONE company right now and evaluate the new ones.

    Does not touch company_list.yaml — use it for ad-hoc checks ("what is open
    at trm-labs on Ashby?") without editing config.

    Args:
        source: ATS name — greenhouse, lever, ashby, workable, recruitee, smartrecruiters
        company: the company's slug on that ATS (e.g. "trm-labs"), or a full
                 custom career domain for Recruitee (e.g. "jobs.channable.com")
    """
    app_context = refreshed_app_context(context)
    with operation_metrics("scan_company"):
        return render_scan_report(
            await discovery_scanning.scan_company(
                source,
                company,
                app_context.config,
                profile=app_context.profile,
                caller=app_context.llm_caller,
            )
        )


@tool_logged
async def add_job(  # noqa: D417 - context is injected by FastMCP; the docstring is the served description
    url: str,
    company: str = "",
    title: str = "",
    *,
    description: str = "",
    context: Context[AppContext, Any],
) -> str:
    """Evaluates a manually provided job and saves it to the database.

    Useful for LinkedIn postings, job posts, or any source not supported by
    the automatic scanner. For Greenhouse and Recruitee URLs, any missing
    'company', 'title', or 'description' is auto-filled from the ATS's own API.
    For everything else, if 'description' is not provided, tries to fetch the
    URL via HTTP (doesn't work for pages requiring authentication, like LinkedIn) —
    'company' and 'title' are still required in that case.

    Args:
        url: job URL (required, used as unique identifier)
        company: company name (e.g. "ifood"). Optional for routed ATSes (Greenhouse,
            Recruitee); required otherwise.
        title: job title (e.g. "Senior Software Engineer"). Optional for routed ATSes;
            required otherwise.
        description: job description text. If empty, tries to fetch it automatically.
    """
    app_context = refreshed_app_context(context)
    return await manual_jobs.add_job(
        url,
        company,
        title,
        description,
        app_context.config,
        app_context.profile,
        app_context.llm_caller,
    )


@tool_logged
async def verify_job(  # noqa: D417 - context is injected by FastMCP; the docstring is the served description
    job_id: int,
    page_text: str,
    *,
    context: Context[AppContext, Any],
) -> str:
    """Re-evaluates a job that couldn't be scored automatically because its
    description was empty, using text you copy from its real page.

    Use this when list_jobs(status="needs_review") shows a pending job: open
    its URL, select the whole page (Cmd+A), copy it (Cmd+C), and pass that
    text here. The job is scored with the same evaluator as any other job
    and moves to 'new' or 'archived' depending on the configured threshold.

    Args:
        job_id: the pending job's ID (from list_jobs(status="needs_review") or get_job)
        page_text: the copied page text — becomes the job's real description
    """  # noqa: D205 - served verbatim as the MCP tool description
    app_context = refreshed_app_context(context)
    return await manual_jobs.verify_job(
        job_id,
        page_text,
        app_context.config,
        profile=app_context.profile,
        caller=app_context.llm_caller,
    )


@tool_logged
async def archive_stale_jobs(  # noqa: D417 - context is injected by FastMCP; the docstring is the served description
    job_id: int | None = None,
    company: str | None = None,
    *,
    context: Context[AppContext, Any],
) -> str:
    """Detect and archive (status='archived', closed_at set) jobs that disappeared from their source.

    Checks jobs currently in new/reviewed/applying/needs_review against the source's
    current listing (Greenhouse/Lever/Ashby API, or a LinkedIn page revisit). A company
    whose check fails (network error, malformed response) is reported explicitly and left
    untouched — never silently archived by mistake. A job with no listing to compare
    against (added by URL, source='manual') is listed with its link for the person to
    confirm by hand, and is never archived.

    Args:
        job_id: check only this job (mutually exclusive with company).
        company: check only jobs from this company, case-insensitive (mutually exclusive
                 with job_id).
    """
    app_context = refreshed_app_context(context)
    try:
        result = await archive.archive_stale_jobs(job_id, company, app_context.config)
    except ArchiveStaleJobsError as error:
        return str(error)
    return format_archive_result(result)
