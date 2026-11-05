"""scan_and_evaluate archives stale jobs last and attaches the result."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import init_db
from moonlighter.discovery.scan.scanning import scan_and_evaluate

from tests.discovery.scan_fakes import make_raw_job


async def test_scan_and_evaluate_archives_last_and_attaches_the_result(temporary_database):
    init_db()
    order = []
    raw_job = make_raw_job(1)

    async def evaluate(new_jobs, config, profile, *, caller):
        order.append("evaluate")
        return [], False

    async def archive(job_id, company, config):
        order.append("archive")
        return "the-archive-result"

    with (
        patch("moonlighter.discovery.scan.scanning.load_company_list", return_value={}),
        patch(
            "moonlighter.discovery.scan.scanning.collect_raw_jobs",
            new=AsyncMock(return_value=([raw_job], "a warning")),
        ),
        patch("moonlighter.discovery.scan.scanning.evaluate_and_store", new=evaluate),
        patch("moonlighter.discovery.scan.scanning.archive_stale_jobs", new=archive),
    ):
        report = await scan_and_evaluate("kw", "all", {"score_threshold": 6.5}, {}, MagicMock())
    assert order == ["evaluate", "archive"]
    assert report.archive == "the-archive-result"
    assert report.warning == "a warning"
