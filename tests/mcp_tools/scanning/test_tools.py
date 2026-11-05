"""scan_company, add_job, verify_job and archive_stale_jobs hand off to their services and format the answer."""

from unittest.mock import AsyncMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.archive import ArchiveResult, ArchiveStaleJobsError
from moonlighter.discovery.results import ScanKind, ScanReport
from moonlighter.mcp_tools.scanning import add_job, archive_stale_jobs, scan_company, verify_job

from tests._context import make_test_context
from tests.mcp_tools._records import make_eval_result


async def test_scan_company_tool_delegates_to_service(temporary_database):
    init_db()

    fake_report = ScanReport(kind=ScanKind.UNKNOWN_SOURCE, threshold=6.5, error="report")
    with patch(
        "moonlighter.discovery.scanning.scan_company", new=AsyncMock(return_value=fake_report)
    ) as mock_scan_company:
        result = await scan_company("greenhouse", "stripe", context=make_test_context())
    assert result == "report"
    mock_scan_company.assert_awaited_once()
    call_arguments = mock_scan_company.await_args.args
    assert call_arguments[0] == "greenhouse"
    assert call_arguments[1] == "stripe"


async def test_add_job_tool_delegates_to_service(temporary_database):
    """O wrapper MCP add_job delega ao manual_jobs.add_job e devolve o resultado."""
    init_db()

    with patch(
        "moonlighter.discovery.manual_jobs.evaluate_job",
        new=AsyncMock(return_value=make_eval_result(8.0)),
    ):
        result = await add_job(
            url="https://x.com/manual/tool/1",
            company="Stripe",
            title="Eng",
            description="A detailed job description that goes on.",
            context=make_test_context(),
        )
    assert "Stripe" in result or "NEW" in result


async def test_verify_job_tool_delegates_to_service(temporary_database):
    """The verify_job MCP wrapper delegates to manual_jobs.verify_job and returns the result."""
    init_db()

    job = Job.create(
        source="inhire",
        company="Alice",
        title="Squad Manager",
        url="https://alice.inhire.app/vagas/2",
        status="needs_review",
        score=None,
    )
    with patch(
        "moonlighter.discovery.manual_jobs.evaluate_job",
        new=AsyncMock(return_value=make_eval_result(8.0)),
    ):
        result = await verify_job(
            job_id=job.id,
            page_text="Full page text with the real job description.",
            context=make_test_context(),
        )
    assert "Alice" in result or "NEW" in result


async def test_tool_archive_stale_jobs_delegates_and_formats(temporary_database):
    init_db()

    fake_result = ArchiveResult(
        archived=[{"company": "acme", "title": "Engineer", "url": "https://x.com/1"}],
        failed_companies=["beta"],
    )
    with patch(
        "moonlighter.discovery.archive.archive_stale_jobs",
        new=AsyncMock(return_value=fake_result),
    ):
        result = await archive_stale_jobs(context=make_test_context())

    assert "acme" in result
    assert "beta" in result


async def test_tool_archive_stale_jobs_passes_filters(temporary_database):
    init_db()

    mock_service = AsyncMock(return_value=ArchiveResult())
    with patch("moonlighter.discovery.archive.archive_stale_jobs", new=mock_service):
        await archive_stale_jobs(job_id=123, company=None, context=make_test_context())

    mock_service.assert_awaited_once()
    call_arguments = mock_service.await_args.args
    assert call_arguments[0] == 123
    assert call_arguments[1] is None


async def test_tool_archive_stale_jobs_rejects_both_filters(temporary_database):
    init_db()

    with patch(
        "moonlighter.discovery.archive.archive_stale_jobs",
        new=AsyncMock(side_effect=ArchiveStaleJobsError("Provide job_id OR company, not both.")),
    ):
        result = await archive_stale_jobs(job_id=1, company="acme", context=make_test_context())

    assert "OR company" in result
