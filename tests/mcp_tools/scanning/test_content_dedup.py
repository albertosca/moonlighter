"""One posting under three URLs costs one evaluation, now and on the next scan."""

from unittest.mock import AsyncMock

from moonlighter.core.db import Job, ScanLog, init_db
from moonlighter.discovery.sources.base import RawJob
from moonlighter.mcp_tools.scanning import scan_and_evaluate
from tests._context import make_test_context
from tests.mcp_tools._records import make_eval_result
from tests.mcp_tools.scanning.test_deduplication import _scan_patches

TEXT = "AgenticOps engineer, remote, building the agent platform end to end."
URLS = ["https://x/agenticops", "https://x/agenticops-9", "https://x/agenticops-10"]


def _raw_jobs():
    return [
        RawJob(source="greenhouse", company="Tether", title="AgenticOps", url=url, description=TEXT)
        for url in URLS
    ]


async def test_three_urls_with_one_text_are_one_job(temporary_database):
    init_db()
    eval_mock = AsyncMock(return_value=make_eval_result(score=8.0))
    with _scan_patches(_raw_jobs(), eval_mock):
        await scan_and_evaluate(context=make_test_context())
    assert eval_mock.call_count == 1
    assert [job.url for job in Job.select()] == [URLS[0]]
    assert ScanLog.select().where(ScanLog.job_url.in_(URLS[1:])).count() == 0

    with _scan_patches(_raw_jobs(), eval_mock):
        await scan_and_evaluate(context=make_test_context())
    original = Job.get(Job.url == URLS[0])
    copies = Job.select().where(Job.url.in_(URLS[1:])).order_by(Job.url)
    assert [(job.status, job.duplicate_of_id) for job in copies] == [
        ("archived", original.id),
        ("archived", original.id),
    ]
    assert eval_mock.call_count == 1
