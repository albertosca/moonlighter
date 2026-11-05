"""The one metrics line a scan logs and the spend-limit counter."""

import logging
from unittest.mock import AsyncMock, patch

from moonlighter.core.db import init_db
from moonlighter.core.metrics import record_call
from moonlighter.discovery.sources.base import RawJob
from moonlighter.mcp_tools.scanning import scan_and_evaluate
from tests._context import make_test_context
from tests.mcp_tools._records import make_eval_result


async def test_scan_and_evaluate_logs_one_metrics_summary(temporary_database, caplog):
    """With a stubbed evaluate_jobs_batch that records one LLM call per job (as the
    real evaluator/caller would), scan_and_evaluate must emit exactly one
    `op=scan_and_evaluate` summary line naming the right call count — proof the
    tool wraps its whole body in a single operation_metrics scope, not one
    scope per job/batch (which would split the counts across many lines).
    """
    init_db()

    raws = [
        RawJob(
            source="greenhouse",
            company=f"Co{index}",
            title="Eng",
            url=f"https://x.com/metrics/{index}",
            description="A detailed job description that goes on.",
        )
        for index in range(3)
    ]

    async def _batch_records_calls(jobs, profile, model, *, caller):
        result = make_eval_result(score=8.0)
        out = []
        for _ in jobs:
            record_call(0.01, input_tokens=1, output_tokens=2)
            out.append(result)
        return out

    with (
        caplog.at_level(logging.INFO),
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.scan.pipeline.evaluate_jobs_batch", new=_batch_records_calls),
        patch(
            "moonlighter.discovery.scan.scanning.load_company_list",
            return_value={"greenhouse": ["co"]},
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=raws)
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(context=make_test_context())

    summary_lines = [
        record for record in caplog.records if "op=scan_and_evaluate" in record.getMessage()
    ]
    assert len(summary_lines) == 1
    summary_message = summary_lines[0].getMessage()
    assert "calls=3" in summary_message
    assert "spend_limit_hits=0" in summary_message


async def test_scan_and_evaluate_spend_limit_abort_increments_hits(temporary_database, caplog):
    """A spend-limit abort mid-scan increments spend_limit_hits in the single
    scan_and_evaluate summary (evaluator/service call record_spend_limit_hit()
    before propagating, inside the tool's one operation_metrics scope).
    """
    init_db()

    raws = [
        RawJob(
            source="greenhouse",
            company="co",
            title="Eng",
            url="https://x.com/quota/1",
            description="A detailed job description that goes on.",
        )
    ]

    async def _batch_raises_spend_limit(jobs, profile, model, *, caller):
        # Deliberately does NOT call record_spend_limit_hit() itself — the
        # production `except is_spend_limit(e)` catch site in
        # moonlighter.discovery.scan.pipeline is what must record the hit, exactly
        # once, before propagating.
        raise RuntimeError("spend limit reached")

    with (
        caplog.at_level(logging.INFO),
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.scan.pipeline.evaluate_jobs_batch", new=_batch_raises_spend_limit
        ),
        patch(
            "moonlighter.discovery.scan.scanning.load_company_list",
            return_value={"greenhouse": ["co"]},
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=raws)
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(context=make_test_context())

    summary_lines = [
        record for record in caplog.records if "op=scan_and_evaluate" in record.getMessage()
    ]
    assert len(summary_lines) == 1
    assert "spend_limit_hits=1" in summary_lines[0].getMessage()
