"""How scan_and_evaluate behaves across batches: all processed, a failing evaluation, a crashing chunk."""

from unittest.mock import AsyncMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.sources.base import RawJob
from moonlighter.mcp_tools.scanning import scan_and_evaluate

from tests._context import make_test_context
from tests.mcp_tools._records import batch_of, make_eval_result


async def test_scan_concurrent_batch_all_processed(temporary_database):
    """15 jobs → 3 chunks of 5 (scan_batch_size=5) → evaluate_jobs_batch called 3× → all 15 in DB."""
    init_db()

    raws = [
        RawJob(
            source="greenhouse",
            company=f"Co{index}",
            title="Eng",
            url=f"https://x.com/batch/{index}",
            description="A detailed job description that goes on.",
        )
        for index in range(15)
    ]
    mock_batch = AsyncMock(side_effect=batch_of(make_eval_result(score=7.0)))
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
        await scan_and_evaluate(context=make_test_context())
    # chunking assertion: 15 jobs / batch_size=5 → exactly 3 calls to evaluate_jobs_batch
    assert mock_batch.call_count == 3, (
        f"expected 3 chunks, but evaluate_jobs_batch was called {mock_batch.call_count}x "
        f"(chunking loop broken?)"
    )
    assert Job.select().count() == 15


async def test_scan_non_spend_error_keeps_title_filtered_in_report(temporary_database):
    """A generic (non-spend-limit) error in evaluate_jobs_batch must not drop the
    title-filtered jobs already persisted earlier in the same chunk from the report
    count — they're already saved in the DB, the report must reflect that too."""
    init_db()

    raws = [
        RawJob(
            source="greenhouse",
            company="co",
            title="Staff Accountant",
            url="https://x.com/nonspend/1",
            description="A detailed job description that goes on.",
        ),
        RawJob(
            source="greenhouse",
            company="co",
            title="Eng",
            url="https://x.com/nonspend/2",
            description="A detailed job description that goes on.",
        ),
    ]
    mock_batch = AsyncMock(side_effect=Exception("unexpected LLM error"))

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
        result = await scan_and_evaluate(
            context=make_test_context(
                config={
                    "score_threshold": 6.5,
                    "llm_model": "claude-haiku-4-5-20251001",
                    "title_blocklist": ["staff accountant"],
                    "scan_concurrency": 1,
                    "scan_batch_size": 2,
                }
            )
        )

    # Already true today: the title-filtered job is persisted regardless of the bug.
    filtered_job = Job.get(Job.url == "https://x.com/nonspend/1")
    assert filtered_job.status == "archived"
    # The bug: the report text undercounts it as 0 instead of 1.
    assert "1 filtered by title" in result, (
        f"expected the title-filtered job to be counted in the report even with a "
        f"non-spend-limit error in the batch; report: {result!r}"
    )


async def test_scan_chunk_crash_outside_try_except_does_not_break_whole_scan(temporary_database):
    """A bug that crashes evaluate_chunk itself (outside its own try/except, e.g. a
    _persist failure) must not blow up the whole scan_and_evaluate call — gather's
    return_exceptions=True catches it, this chunk contributes nothing, other chunks
    are unaffected."""
    init_db()

    raws = [
        RawJob(
            source="greenhouse",
            company="co",
            title="Eng",
            url="https://x.com/crash/1",
            description="A detailed job description that goes on.",
        ),
    ]

    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.screening.claim", side_effect=Exception("db corrupted")),
        patch(
            "moonlighter.discovery.scanning.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=raws)
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(
            context=make_test_context(
                config={
                    "score_threshold": 6.5,
                    "llm_model": "claude-haiku-4-5-20251001",
                    "title_blocklist": [],
                    "scan_concurrency": 1,
                    "scan_batch_size": 5,
                }
            )
        )  # must not raise

    assert Job.select().count() == 0
    assert "0 jobs processed" in result
