"""Hitting the spend limit mid-scan leaves no orphan claims and stops the batches after it."""

from unittest.mock import AsyncMock, patch

from moonlighter.core.db import Job, ScanLog, init_db
from moonlighter.discovery.sources.base import RawJob
from moonlighter.mcp_tools.scanning import scan_and_evaluate

from tests._context import make_test_context


async def test_scan_spend_limit_midbatch_leaves_no_orphan_claims(temporary_database):
    """INVARIANT: when a spend limit is hit inside a chunk, no ScanLog may be left
    without a matching Job (otherwise the job disappears from the pipeline forever).

    Uses scan_batch_size=4 with 8 jobs (2 chunks of 4) and scan_concurrency=1
    to serialize: chunk 0 calls evaluate_jobs_batch (which raises spend-limit),
    the `for raw in to_eval: _release(raw)` loop runs for the chunk's 4 jobs,
    and chunk 1 sees the stop event and touches nothing else.

    This test FAILS if the _release loop is removed from the spend-limit except
    clause: without release, chunk 0's 4 jobs end up with a ScanLog but no Job.
    """
    init_db()

    raws = [
        RawJob(
            source="greenhouse",
            company=f"Co{index}",
            title="Eng",
            url=f"https://x.com/orphan/{index}",
            description="A detailed job description that goes on.",
        )
        for index in range(8)
    ]

    spend_limit_error = Exception("You've hit your monthly spend limit")
    mock_batch = AsyncMock(side_effect=spend_limit_error)

    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.pipeline.evaluate_jobs_batch", new=mock_batch),
        patch(
            "moonlighter.discovery.scanning.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=raws)
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(
            context=make_test_context(
                config={
                    "score_threshold": 6.5,
                    "llm_model": "claude-haiku-4-5-20251001",
                    "title_blocklist": [],
                    "scan_concurrency": 1,
                    "scan_batch_size": 4,
                }
            )
        )

    job_urls = {job.url for job in Job.select()}
    orphans = [
        scan_log.job_url for scan_log in ScanLog.select() if scan_log.job_url not in job_urls
    ]
    assert orphans == [], f"orphan claims (claim without Job): {orphans}"


async def test_scan_spend_limit_stops_further_batches(temporary_database):
    """When batch 1 hits the spend limit, the following batches are not attempted.

    With scan_concurrency=1 the chunks are serialized: chunk 0 calls
    evaluate_jobs_batch (which raises spend-limit), sets the stop event, and
    releases the semaphore; chunks 1 and 2 see the stop before calling
    evaluate_jobs_batch. Concrete proof of early stop: call_count == 1, not 3.
    """
    init_db()

    raws = [
        RawJob(
            source="greenhouse",
            company=f"Co{index}",
            title="Eng",
            url=f"https://x.com/stop/{index}",
            description="A detailed job description that goes on.",
        )
        for index in range(15)  # 3 batches of 5 with scan_batch_size=5
    ]

    spend_limit_error = Exception("usage limit reached")
    mock_batch = AsyncMock(side_effect=spend_limit_error)

    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.pipeline.evaluate_jobs_batch", new=mock_batch),
        patch(
            "moonlighter.discovery.scanning.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=raws)
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(
            context=make_test_context(
                config={
                    "score_threshold": 6.5,
                    "llm_model": "claude-haiku-4-5-20251001",
                    "title_blocklist": [],
                    "scan_concurrency": 1,
                    "scan_batch_size": 5,
                }
            )
        )

    # With scan_concurrency=1 the stop prevents batches 2 and 3 from calling the LLM.
    # call_count should be 1 (not 3 = total batches).
    assert mock_batch.call_count == 1, (
        f"expected 1 call to evaluate_jobs_batch, but there were {mock_batch.call_count} "
        f"(batches 2 and 3 should have been stopped by the stop event)"
    )
    # and no orphan claim remained
    job_urls = {job.url for job in Job.select()}
    assert all(scan_log.job_url in job_urls for scan_log in ScanLog.select())
