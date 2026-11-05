import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

# Timing rules for this file. A timing assertion compares two measurements taken
# in the same run, never a number of seconds: a load average far above the core
# count slows both sides alike, so a ratio survives it and a wall-clock limit does
# not (2026-11-01: three absolute limits went red at load ~30). Each test also
# asserts the work actually happened, because a swallowed error is fast.

CONCURRENCY_RATIO = 0.5  # concurrent must take less than half the sequential time
DELAY_SECONDS = 0.02


def _slow_client(payload):
    """Async-context client whose GET answers `payload` after DELAY_SECONDS."""

    async def slow_get(url, **keyword_arguments):
        await asyncio.sleep(DELAY_SECONDS)
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = payload
        return response

    client = MagicMock()
    client.get = slow_get
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


async def _assert_scan_is_concurrent(scanner, source, payload, company_count):
    """Scan `company_count` slugs at once, then one by one, and compare."""
    from moonlighter.discovery.sources.base import SourceStats

    slugs = [f"company-{index}" for index in range(company_count)]
    client = _slow_client(payload)
    stats = {}

    with patch(
        "moonlighter.discovery.sources.company_boards.gathering.httpx.AsyncClient",
        return_value=client,
    ):
        start_time = time.perf_counter()
        await scanner.scan(slugs, stats=stats)
        concurrent_elapsed = time.perf_counter() - start_time

        start_time = time.perf_counter()
        for slug in slugs:
            await scanner.scan([slug])
        sequential_elapsed = time.perf_counter() - start_time

    # Zero errors is what proves the mocked fetch really ran: a mock the scanner
    # never calls makes every company fail, quickly, and the timing still "passes".
    assert stats[source] == SourceStats(companies=company_count, jobs=0, errors=0)
    assert concurrent_elapsed < sequential_elapsed * CONCURRENCY_RATIO, (
        f"{source}: concurrent {concurrent_elapsed:.3f}s should be under "
        f"{CONCURRENCY_RATIO:.0%} of sequential {sequential_elapsed:.3f}s"
    )


# ── Scan concorrente ──────────────────────────────────────────────────────────


async def test_greenhouse_scan_20_companies_concurrent():
    from moonlighter.discovery.sources.company_boards.greenhouse import GreenhouseScanner

    await _assert_scan_is_concurrent(GreenhouseScanner(), "greenhouse", {"jobs": []}, 20)


async def test_lever_scan_15_companies_concurrent():
    from moonlighter.discovery.sources.company_boards.lever import LeverScanner

    await _assert_scan_is_concurrent(LeverScanner(), "lever", [], 15)


async def test_ashby_scan_10_companies_concurrent():
    """Ashby is fetched with GET (the REST posting API), not the retired GraphQL POST."""
    from moonlighter.discovery.sources.company_boards.ashby import AshbyScanner

    await _assert_scan_is_concurrent(AshbyScanner(), "ashby", {"jobs": []}, 10)


# ── Batch LLM evaluation ─────────────────────────────────────────────────────


async def test_evaluate_10_jobs_concurrent_faster_than_sequential():
    """
    10 LLM evaluations in asyncio.gather should be much faster than sequential.
    Each mock evaluation has 0.05s delay.
    Sequential: ~0.5s. Concurrent: ~0.05s.
    """
    import json

    from moonlighter.discovery.evaluation.single import evaluate_job

    call_count = [0]
    _response = json.dumps(
        {
            "score": 7.0,
            "score_notes": "ok",
            "caveats": [],
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_source": None,
        }
    )

    async def slow_caller(prompt, model, cache_prefix=None):
        await asyncio.sleep(0.05)
        call_count[0] += 1
        return _response

    profile = {}
    jobs = [(f"Co{index}", f"Eng {index}", f"Job description {index}") for index in range(10)]

    start_time = time.perf_counter()
    await asyncio.gather(
        *[
            evaluate_job(
                company=company,
                title=title,
                description=description,
                profile=profile,
                model="test",
                _caller=slow_caller,
                location=None,
                remote_type=None,
            )
            for company, title, description in jobs
        ]
    )
    concurrent_elapsed = time.perf_counter() - start_time

    # Sequential baseline (just measure)
    start_time = time.perf_counter()
    for company, title, description in jobs:
        await evaluate_job(
            company=company,
            title=title,
            description=description,
            profile=profile,
            model="test",
            _caller=slow_caller,
            location=None,
            remote_type=None,
        )
    sequential_elapsed = time.perf_counter() - start_time

    assert call_count[0] == 2 * len(jobs)  # both passes really called the model
    assert concurrent_elapsed < sequential_elapsed * CONCURRENCY_RATIO, (
        f"Concurrent ({concurrent_elapsed:.3f}s) should be at least 2x faster than sequential ({sequential_elapsed:.3f}s)"
    )


async def test_evaluate_batch_size_10_processes_all():
    """
    25 jobs processed in batches of 10 (as scan_and_evaluate does) — all 25 processed.
    """
    import json

    from moonlighter.discovery.evaluation.single import evaluate_job

    _response = json.dumps(
        {
            "score": 7.0,
            "score_notes": "ok",
            "caveats": [],
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_source": None,
        }
    )

    async def fast_caller(prompt, model, cache_prefix=None):
        return _response

    profile = {}
    BATCH_SIZE = 10
    all_jobs = [(f"Co{index}", f"Eng{index}", f"desc{index}") for index in range(25)]
    results = []

    for index in range(0, len(all_jobs), BATCH_SIZE):
        batch = all_jobs[index : index + BATCH_SIZE]
        batch_results = await asyncio.gather(
            *[
                evaluate_job(
                    company=company,
                    title=title,
                    description=description,
                    profile=profile,
                    model="test",
                    _caller=fast_caller,
                    location=None,
                    remote_type=None,
                )
                for company, title, description in batch
            ]
        )
        results.extend(batch_results)

    assert len(results) == 25
    assert all(result.score == 7.0 for result in results)


# ── Queries no DB ─────────────────────────────────────────────────────────────
#
# Database cost is checked by counting SQL statements, not seconds: the count does
# not move with machine load, and the regression worth catching here is a query per
# row (or a missing LIMIT), which shows up as a count that grows with the table.


@contextlib.contextmanager
def _count_queries():
    from moonlighter.core.db import db

    with patch.object(db, "execute_sql", wraps=db.execute_sql) as spy:
        yield spy


def _insert_jobs(first_index, last_index):
    from moonlighter.core.db import Job

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
    from moonlighter.core.db import init_db
    from moonlighter.server import list_jobs

    from tests._context import make_test_context

    init_db()
    context = make_test_context()

    async def call_and_count():
        with _count_queries() as spy:
            result = await list_jobs(status="new", limit=20, context=context)
        return result, spy.call_count

    _insert_jobs(0, 100)
    small_result, small_query_count = await call_and_count()
    _insert_jobs(100, 1000)
    large_result, large_query_count = await call_and_count()

    # A tool that raised comes back as a "tool ... failed" line, so check the content.
    assert "failed" not in large_result
    assert small_result.count("Engineer ") == 20
    assert large_result.count("Engineer ") == 20
    assert large_query_count == small_query_count


async def test_drop_already_seen_uses_one_query_whatever_the_scan_log_size(temporary_database):
    """Dedup of 1000 scanned URLs reads ScanLog once and keeps only the unseen job."""
    from moonlighter.core.db import ScanLog, init_db
    from moonlighter.discovery.service import _drop_already_seen
    from moonlighter.discovery.sources.base import RawJob

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
            kept = _drop_already_seen(raw_jobs)
        return kept, spy.call_count

    log_urls(0, 100)
    small_kept, small_query_count = drop_and_count([raw_job(index) for index in range(101)])
    log_urls(100, 1000)
    large_kept, large_query_count = drop_and_count([raw_job(index) for index in range(1001)])

    assert [job.url for job in small_kept] == ["https://example.com/jobs/100"]
    assert [job.url for job in large_kept] == ["https://example.com/jobs/1000"]
    assert small_query_count == large_query_count == 1
