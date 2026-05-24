import time
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Scan concorrente ──────────────────────────────────────────────────────────

async def test_greenhouse_scan_20_companies_concurrent():
    """
    20 companies scanned in parallel should finish much faster than sequential.
    Each mock HTTP call has a 0.02s delay. Sequential: ~0.4s. Concurrent: ~0.02s.
    """
    from candidatador.scanner.http_sources import GreenhouseScanner

    async def slow_get(url, **kwargs):
        await asyncio.sleep(0.02)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"jobs": []}
        return resp

    mock_client = MagicMock()
    mock_client.get = slow_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    slugs = [f"company-{i}" for i in range(20)]

    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        t0 = time.perf_counter()
        await GreenhouseScanner().scan(slugs)
        elapsed = time.perf_counter() - t0

    # Concurrent: should be close to 0.02s (one batch), not 0.4s (20 sequential calls)
    assert elapsed < 0.3, f"Expected < 0.3s (concurrent), got {elapsed:.3f}s"


async def test_lever_scan_15_companies_concurrent():
    """15 Lever companies fetched concurrently."""
    from candidatador.scanner.http_sources import LeverScanner

    async def slow_get(url, **kwargs):
        await asyncio.sleep(0.02)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = []
        return resp

    mock_client = MagicMock()
    mock_client.get = slow_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    slugs = [f"company-{i}" for i in range(15)]

    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        t0 = time.perf_counter()
        await LeverScanner().scan(slugs)
        elapsed = time.perf_counter() - t0

    assert elapsed < 0.3, f"Expected < 0.3s (concurrent), got {elapsed:.3f}s"


async def test_ashby_scan_10_companies_concurrent():
    """10 Ashby companies fetched concurrently via POST."""
    from candidatador.scanner.http_sources import AshbyScanner

    async def slow_post(url, **kwargs):
        await asyncio.sleep(0.02)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": {"jobPostings": []}}
        return resp

    mock_client = MagicMock()
    mock_client.post = slow_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    slugs = [f"company-{i}" for i in range(10)]

    with patch("candidatador.scanner.http_sources.httpx.AsyncClient", return_value=mock_client):
        t0 = time.perf_counter()
        await AshbyScanner().scan(slugs)
        elapsed = time.perf_counter() - t0

    assert elapsed < 0.3, f"Expected < 0.3s (concurrent), got {elapsed:.3f}s"


# ── Avaliação LLM em batch ────────────────────────────────────────────────────

async def test_evaluate_10_jobs_concurrent_faster_than_sequential():
    """
    10 LLM evaluations in asyncio.gather should be much faster than sequential.
    Each mock evaluation has 0.05s delay.
    Sequential: ~0.5s. Concurrent: ~0.05s.
    """
    import json
    from candidatador.evaluator import evaluate_job

    call_count = [0]

    async def slow_evaluate(*args, **kwargs):
        await asyncio.sleep(0.05)
        call_count[0] += 1
        return MagicMock(content=[MagicMock(text=json.dumps({
            "score": 7.0, "score_notes": "ok", "caveats": [],
            "salary_min": None, "salary_max": None,
            "salary_currency": None, "salary_source": None,
        }))])

    mock_client = MagicMock()
    mock_client.messages.create = slow_evaluate

    profile = {}
    jobs = [(f"Co{i}", f"Eng {i}", f"Job description {i}") for i in range(10)]

    t0 = time.perf_counter()
    await asyncio.gather(*[
        evaluate_job(company=c, title=t, description=d, profile=profile, model="test", _client=mock_client)
        for c, t, d in jobs
    ])
    concurrent_elapsed = time.perf_counter() - t0

    # Sequential baseline (just measure)
    t0 = time.perf_counter()
    for c, t, d in jobs:
        await evaluate_job(company=c, title=t, description=d, profile=profile, model="test", _client=mock_client)
    sequential_elapsed = time.perf_counter() - t0

    assert concurrent_elapsed < sequential_elapsed * 0.5, (
        f"Concurrent ({concurrent_elapsed:.3f}s) should be at least 2x faster than sequential ({sequential_elapsed:.3f}s)"
    )
    assert concurrent_elapsed < 0.2, f"Concurrent should finish in < 0.2s, got {concurrent_elapsed:.3f}s"


async def test_evaluate_batch_size_10_processes_all():
    """
    25 jobs processed in batches of 10 (as scan_and_evaluate does) — all 25 processed.
    """
    import json
    from candidatador.evaluator import evaluate_job

    async def fast_evaluate(*args, **kwargs):
        return MagicMock(content=[MagicMock(text=json.dumps({
            "score": 7.0, "score_notes": "ok", "caveats": [],
            "salary_min": None, "salary_max": None,
            "salary_currency": None, "salary_source": None,
        }))])

    mock_client = MagicMock()
    mock_client.messages.create = fast_evaluate

    profile = {}
    BATCH_SIZE = 10
    all_jobs = [(f"Co{i}", f"Eng{i}", f"desc{i}") for i in range(25)]
    results = []

    for i in range(0, len(all_jobs), BATCH_SIZE):
        batch = all_jobs[i:i + BATCH_SIZE]
        batch_results = await asyncio.gather(*[
            evaluate_job(company=c, title=t, description=d, profile=profile, model="test", _client=mock_client)
            for c, t, d in batch
        ])
        results.extend(batch_results)

    assert len(results) == 25
    assert all(r.score == 7.0 for r in results)


# ── Queries no DB ─────────────────────────────────────────────────────────────

async def test_list_jobs_1000_records_fast(tmp_db):
    """list_jobs with 1000 records in DB returns in < 500ms."""
    from candidatador.db import init_db, Job
    init_db()

    # Insert 1000 jobs
    with Job._meta.database.atomic():
        for i in range(1000):
            Job.create(
                source="greenhouse",
                company=f"Company{i}",
                title=f"Engineer {i}",
                url=f"https://example.com/jobs/{i}",
                score=float(i % 10),
                status="new",
            )

    from candidatador.mcp_server import list_jobs
    t0 = time.perf_counter()
    result = await list_jobs(status="new", limit=20)
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.5, f"list_jobs with 1000 records took {elapsed:.3f}s, expected < 0.5s"
    assert result is not None


async def test_scan_log_dedup_1000_urls_fast(tmp_db):
    """Dedup check against ScanLog with 1000 entries completes in < 200ms."""
    from candidatador.db import init_db, ScanLog
    init_db()

    with ScanLog._meta.database.atomic():
        for i in range(1000):
            ScanLog.create(job_url=f"https://example.com/jobs/{i}", source="greenhouse")

    t0 = time.perf_counter()
    seen_urls = {row.job_url for row in ScanLog.select(ScanLog.job_url)}
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.2, f"ScanLog dedup check took {elapsed:.3f}s, expected < 0.2s"
    assert len(seen_urls) == 1000


async def test_generate_answers_concurrent_faster_than_sequential():
    """
    10 generate_answers calls in asyncio.gather should be faster than sequential.
    Each mock call has 0.05s delay. Sequential: ~0.5s. Concurrent: ~0.05s.
    """
    import json
    from candidatador.applicator.base import generate_answers

    async def slow_create(*args, **kwargs):
        await asyncio.sleep(0.05)
        return MagicMock(content=[MagicMock(text=json.dumps({"Why this role?": "Great fit"}))])

    mock_client = MagicMock()
    mock_client.messages.create = slow_create

    profile = {}
    fields = ["Why this role?"]
    calls = [
        generate_answers(company=f"Co{i}", title="Eng", description="desc",
                         fields=fields, profile=profile, model="test", _client=mock_client)
        for i in range(10)
    ]

    t0 = time.perf_counter()
    results = await asyncio.gather(*calls)
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.2, f"Concurrent generate_answers took {elapsed:.3f}s, expected < 0.2s"
    assert all(r.error is None for r in results)
    assert all(r.answers.get("Why this role?") == "Great fit" for r in results)
