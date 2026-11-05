"""What scan_and_evaluate writes onto the job rows it keeps."""

import json
from unittest.mock import AsyncMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.evaluation.models import EvaluationResult
from moonlighter.discovery.sources.base import RawJob
from moonlighter.mcp_tools.scanning import scan_and_evaluate

from tests._context import make_test_context
from tests.mcp_tools._records import batch_of, make_eval_result


async def test_scan_status_archived_if_below_threshold(temporary_database):
    init_db()

    raw = RawJob(
        source="greenhouse",
        company="co",
        title="Eng",
        url="https://x.com/7",
        description="A detailed job description that goes on.",
    )
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.scan.pipeline.evaluate_jobs_batch",
            new=batch_of(make_eval_result(score=3.0)),
        ),
        patch(
            "moonlighter.discovery.scan.scanning.load_company_list",
            return_value={"greenhouse": ["co"]},
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=[raw])
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(context=make_test_context())
    # score=3.0 injetado via evaluate_jobs_batch → status genuinamente "archived"
    job = Job.get(Job.url == "https://x.com/7")
    assert job.status == "archived"


async def test_scan_saves_salary_fields(temporary_database):
    init_db()

    raw = RawJob(
        source="greenhouse",
        company="Stripe",
        title="Eng",
        url="https://x.com/5",
        description="A detailed job description that goes on.",
    )
    eval_result = EvaluationResult(
        score=8.0,
        score_notes="ok",
        caveats=[],
        salary_min=180000,
        salary_max=220000,
        salary_currency="USD",
        salary_source="stated",
    )
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.scan.pipeline.evaluate_jobs_batch",
            new=batch_of(eval_result),
        ),
        patch(
            "moonlighter.discovery.scan.scanning.load_company_list",
            return_value={"greenhouse": ["stripe"]},
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=[raw])
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(context=make_test_context())
    job = Job.get(Job.url == "https://x.com/5")
    assert job.salary_min == 180000
    assert job.salary_currency == "USD"
    assert job.salary_source == "stated"


async def test_scan_saves_caveats_as_json(temporary_database):
    init_db()

    raw = RawJob(
        source="greenhouse",
        company="co",
        title="Eng",
        url="https://x.com/6",
        description="A detailed job description that goes on.",
    )
    eval_result = EvaluationResult(
        score=7.0, score_notes="ok", caveats=["US only", "requires visa"]
    )
    with (
        patch(
            "moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner"
        ) as mock_greenhouse,
        patch("moonlighter.discovery.sources.company_boards.lever.LeverScanner") as mock_lever,
        patch("moonlighter.discovery.sources.company_boards.ashby.AshbyScanner") as mock_ashby,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.scan.pipeline.evaluate_jobs_batch",
            new=batch_of(eval_result),
        ),
        patch(
            "moonlighter.discovery.scan.scanning.load_company_list",
            return_value={"greenhouse": ["co"]},
        ),
    ):
        mock_greenhouse.return_value.scan = AsyncMock(return_value=[raw])
        mock_lever.return_value.scan = AsyncMock(return_value=[])
        mock_ashby.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(context=make_test_context())
    job = Job.get(Job.url == "https://x.com/6")
    caveats = json.loads(job.caveats)
    assert "US only" in caveats
    assert "requires visa" in caveats
