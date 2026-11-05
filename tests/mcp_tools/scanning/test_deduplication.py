"""A URL is evaluated once, however many scans reach it, and the scan log claim is released when a scan stops."""

import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from moonlighter.core.db import Job, ScanLog, init_db
from moonlighter.discovery.sources.base import RawJob
from moonlighter.mcp_tools.scanning import scan_and_evaluate

from tests._context import make_test_context
from tests.mcp_tools._records import make_eval_result


def _scan_patches(raw_jobs, eval_mock):
    """Context manager stack shared by race condition tests."""
    stack = ExitStack()
    stack.enter_context(
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner",
            **{"return_value.scan": AsyncMock(return_value=raw_jobs)},
        )
    )
    stack.enter_context(
        patch(
            "moonlighter.discovery.sources.company_boards.lever.LeverScanner",
            **{"return_value.scan": AsyncMock(return_value=[])},
        )
    )
    stack.enter_context(
        patch(
            "moonlighter.discovery.sources.company_boards.ashby.AshbyScanner",
            **{"return_value.scan": AsyncMock(return_value=[])},
        )
    )
    stack.enter_context(
        patch(
            "moonlighter.core.browser",
            create=True,
            new_page=AsyncMock(side_effect=Exception("no browser")),
        )
    )

    async def _batch(jobs, profile, model, *, caller):
        # Calls eval_mock per job; errors (spend limit) propagate to evaluate_chunk.
        return [
            await eval_mock(job.company, job.title, job.description, profile, model, caller)
            for job in jobs
        ]

    stack.enter_context(
        patch("moonlighter.discovery.scan.pipeline.evaluate_jobs_batch", new=_batch)
    )
    stack.enter_context(
        patch(
            "moonlighter.discovery.scan.scanning.load_company_list",
            return_value={"greenhouse": ["co"]},
        )
    )
    return stack


async def test_scan_concurrent_calls_evaluate_same_url_only_once(temporary_database):
    """Concurrent scan_and_evaluate calls must not call evaluate_job twice for the same URL.

    Reproduces the race condition where 11 parallel MCP tool invocations each saw
    the same empty ScanLog snapshot and fired 11 LLM calls per job.
    """
    init_db()

    url = "https://x.com/race-1"
    raw = RawJob(
        source="greenhouse",
        company="Co",
        title="Eng",
        url=url,
        description="A detailed job description that goes on.",
    )
    eval_mock = AsyncMock(return_value=make_eval_result(score=8.0))

    with _scan_patches([raw], eval_mock):
        # Fire 5 concurrent scans for the same job
        await asyncio.gather(*[scan_and_evaluate(context=make_test_context()) for _ in range(5)])

    # LLM must have been called exactly once despite 5 concurrent scans
    assert eval_mock.call_count == 1
    # Exactly one Job and one ScanLog entry
    assert Job.select().where(Job.url == url).count() == 1
    assert ScanLog.select().where(ScanLog.job_url == url).count() == 1


async def test_scan_spend_limit_releases_scan_log_claim(temporary_database):
    """When evaluate_job hits the spend limit, the scan STOPS CLEANLY (does not crash):
    it releases the claim in ScanLog (URL retryable on the next scan), does not create
    a Job, and warns in the return. Conservative contract — no exception propagates to the tool.
    """
    init_db()

    url = "https://x.com/spend-limit-1"
    raw = RawJob(
        source="greenhouse",
        company="Co",
        title="Eng",
        url=url,
        description="A detailed job description that goes on.",
    )
    spend_limit_error = Exception(
        "claude CLI exited with code 1: You've hit your monthly spend limit"
    )
    failing_eval = AsyncMock(side_effect=spend_limit_error)

    with _scan_patches([raw], failing_eval):
        result = await scan_and_evaluate(context=make_test_context())

    # Does not raise — reports the limit in the return text.
    assert "spend limit" in result.lower() or "interrompido" in result.lower()
    # Claim released — empty ScanLog so the next scan can retry the URL.
    assert ScanLog.select().where(ScanLog.job_url == url).count() == 0
    # Nenhum Job criado.
    assert Job.select().where(Job.url == url).count() == 0


async def test_scan_already_in_scan_log_skips_llm(temporary_database):
    """URL already in ScanLog at scan start → evaluate_job not called (existing dedup)."""
    init_db()
    ScanLog.create(job_url="https://x.com/already-seen", source="greenhouse")

    raw = RawJob(source="greenhouse", company="Co", title="Eng", url="https://x.com/already-seen")
    eval_mock = AsyncMock(return_value=make_eval_result(score=8.0))

    with _scan_patches([raw], eval_mock):
        await scan_and_evaluate(context=make_test_context())

    eval_mock.assert_not_called()


async def test_scan_dedup_against_scan_log(temporary_database):
    init_db()
    ScanLog.create(job_url="https://x.com/3", source="greenhouse")

    raw = RawJob(source="greenhouse", company="co", title="Eng", url="https://x.com/3")
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.scan.pipeline.evaluate_jobs_batch") as mock_batch,
        patch(
            "moonlighter.discovery.scan.scanning.load_company_list",
            return_value={"greenhouse": ["co"]},
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=[raw])
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(context=make_test_context())
    # evaluate_jobs_batch is genuinely not called: the scanner returned the job but
    # dedup (a pre-existing ScanLog) filtered it before it reached evaluate_and_store.
    mock_batch.assert_not_called()
    assert "No new jobs found" in result
