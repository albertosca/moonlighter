"""Database cost is bounded by the query count, whatever the table size."""

import contextlib
from unittest.mock import patch

from moonlighter.core.db import Job, ScanLog, db, init_db
from moonlighter.discovery.scan.claims import drop_already_seen
from moonlighter.discovery.sources.base import RawJob
from moonlighter.mcp_tools.jobs import list_jobs

# Database cost is checked by counting SQL statements, not seconds: the count does
# not move with machine load, and the regression worth catching here is a query per
# row (or a missing LIMIT), which shows up as a count that grows with the table.


@contextlib.contextmanager
def _count_queries():
    with patch.object(db, "execute_sql", wraps=db.execute_sql) as spy:
        yield spy


def _insert_jobs(first_index, last_index):
    with Job._meta.database.atomic():
        for index in range(first_index, last_index):
            Job.create(
                source="greenhouse",
                company=f"Company{index}",
                title=f"Engineer {index}",
                url=f"https://example.com/jobs/{index}",
                score=float(index % 10),
                status="new",
            )


async def test_list_jobs_returns_one_page_with_a_query_count_independent_of_table_size(
    temporary_database,
):
    """100 or 1000 rows in the table: the same number of queries, and only `limit` rows out."""
    init_db()

    async def call_and_count():
        with _count_queries() as spy:
            result = await list_jobs(status="new", limit=20)
        return result, spy.call_count

    _insert_jobs(0, 100)
    small_result, small_query_count = await call_and_count()
    _insert_jobs(100, 1000)
    large_result, large_query_count = await call_and_count()

    # A tool that raised comes back as a "tool ... failed" line, so check the content.
    assert "failed" not in large_result
    assert small_result.count("Engineer ") == 20
    assert large_result.count("Engineer ") == 20
    # The spy must see the queries at all: a list_jobs that bypassed it would make 0 == 0 pass.
    assert small_query_count >= 1
    assert large_query_count == small_query_count


async def test_drop_already_seen_uses_one_query_whatever_the_scan_log_size(temporary_database):
    """Dedup of 1000 scanned URLs reads ScanLog once and keeps only the unseen job."""
    init_db()

    def raw_job(index):
        return RawJob(
            source="greenhouse",
            company="Acme",
            title=f"Engineer {index}",
            url=f"https://example.com/jobs/{index}",
        )

    def log_urls(first_index, last_index):
        with ScanLog._meta.database.atomic():
            for index in range(first_index, last_index):
                ScanLog.create(job_url=f"https://example.com/jobs/{index}", source="greenhouse")

    def drop_and_count(raw_jobs):
        with _count_queries() as spy:
            kept = drop_already_seen(raw_jobs)
        return kept, spy.call_count

    log_urls(0, 100)
    small_kept, small_query_count = drop_and_count([raw_job(index) for index in range(101)])
    log_urls(100, 1000)
    large_kept, large_query_count = drop_and_count([raw_job(index) for index in range(1001)])

    assert [job.url for job in small_kept] == ["https://example.com/jobs/100"]
    assert [job.url for job in large_kept] == ["https://example.com/jobs/1000"]
    assert small_query_count == large_query_count == 1
