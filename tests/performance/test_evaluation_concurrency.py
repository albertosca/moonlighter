"""Evaluating jobs with the LLM runs concurrently and processes every job."""

import asyncio
import json
import time

from moonlighter.discovery.evaluation.single import evaluate_job
from tests.performance.timing import CONCURRENCY_RATIO

_MODEL_ANSWER = json.dumps(
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


async def _evaluate(job, profile, caller):
    company, title, description = job
    return await evaluate_job(
        company=company,
        title=title,
        description=description,
        profile=profile,
        model="test",
        _caller=caller,
        location=None,
        remote_type=None,
    )


async def test_evaluate_10_jobs_concurrent_faster_than_sequential():
    """10 LLM evaluations in asyncio.gather should be much faster than sequential.

    Each mock evaluation has 0.05s delay.
    Sequential: ~0.5s. Concurrent: ~0.05s.
    """
    call_count = 0

    async def slow_caller(prompt, model, cache_prefix=None):
        nonlocal call_count
        await asyncio.sleep(0.05)
        call_count += 1
        return _MODEL_ANSWER

    profile = {}
    jobs = [(f"Co{index}", f"Eng {index}", f"Job description {index}") for index in range(10)]

    start_time = time.perf_counter()
    await asyncio.gather(*[_evaluate(job, profile, slow_caller) for job in jobs])
    concurrent_elapsed = time.perf_counter() - start_time

    # Sequential baseline (just measure)
    start_time = time.perf_counter()
    for job in jobs:
        await _evaluate(job, profile, slow_caller)
    sequential_elapsed = time.perf_counter() - start_time

    assert call_count == 2 * len(jobs)  # both passes really called the model
    assert concurrent_elapsed < sequential_elapsed * CONCURRENCY_RATIO, (
        f"Concurrent ({concurrent_elapsed:.3f}s) should be at least 2x faster than sequential ({sequential_elapsed:.3f}s)"
    )


async def test_evaluate_batch_size_10_processes_all():
    """25 jobs processed in batches of 10 (as scan_and_evaluate does) — all 25 processed."""

    async def fast_caller(prompt, model, cache_prefix=None):
        return _MODEL_ANSWER

    profile = {}
    batch_size = 10
    all_jobs = [(f"Co{index}", f"Eng{index}", f"desc{index}") for index in range(25)]
    results = []

    for index in range(0, len(all_jobs), batch_size):
        batch = all_jobs[index : index + batch_size]
        batch_results = await asyncio.gather(
            *[_evaluate(job, profile, fast_caller) for job in batch]
        )
        results.extend(batch_results)

    assert len(results) == 25
    assert all(result.score == 7.0 for result in results)
