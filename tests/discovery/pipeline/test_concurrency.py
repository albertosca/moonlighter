"""A scan runs its batches concurrently, capped, and sized by its defaults."""

import asyncio
from unittest.mock import MagicMock, patch

from moonlighter.core.db import init_db
from moonlighter.discovery.pipeline import evaluate_and_store

from tests.discovery.scan_fakes import BatchRecorder, make_raw_job, store_config


class _Tracker:
    """Caller that tracks the peak of concurrent LLM calls."""

    def __init__(self) -> None:
        self.current = 0
        self.peak = 0

    async def __call__(self, prompt: str, model: str, cache_prefix: str | None = None) -> str:
        self.current += 1
        self.peak = max(self.peak, self.current)
        await asyncio.sleep(0.01)
        self.current -= 1
        return '{"score": 8.0, "score_notes": "ok", "caveats": []}'


async def test_scan_concurrency_is_capped(temporary_database):
    init_db()
    caller = _Tracker()
    config = {
        "score_threshold": 6.5,
        "eval_model": "m",
        "scan_concurrency": 2,
        "scan_batch_size": 1,
        "title_blocklist": [],
    }
    jobs = [make_raw_job(index) for index in range(6)]
    saved, spend_hit = await evaluate_and_store(jobs, config, {}, caller=caller)
    assert len(saved) == 6
    assert spend_hit is False
    assert caller.peak == 2


async def test_scan_batches_jobs_into_one_call(temporary_database):
    init_db()
    calls = {"n": 0}

    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        calls["n"] += 1
        return (
            "["
            + ", ".join('{"score": 8.0, "score_notes": "ok", "caveats": []}' for _ in range(4))
            + "]"
        )

    config = {
        "score_threshold": 6.5,
        "eval_model": "m",
        "scan_concurrency": 5,
        "scan_batch_size": 4,
        "title_blocklist": [],
    }
    jobs = [make_raw_job(index) for index in range(4)]
    saved, spend_hit = await evaluate_and_store(jobs, config, {}, caller=caller)
    assert len(saved) == 4
    assert spend_hit is False
    assert calls["n"] == 1  # 4 jobs, 1 batch, 1 call


async def test_a_default_batch_holds_five_jobs(temporary_database):
    init_db()
    recorder = BatchRecorder()
    with patch("moonlighter.discovery.pipeline.evaluate_jobs_batch", new=recorder):
        await evaluate_and_store(
            [make_raw_job(index) for index in range(7)],
            store_config(scan_concurrency=1),
            {},
            caller=MagicMock(),
        )
    assert recorder.sizes == [5, 2]


async def test_default_concurrency_is_five_batches_at_once(temporary_database):
    init_db()
    caller = _Tracker()
    saved, _ = await evaluate_and_store(
        [make_raw_job(index) for index in range(8)],
        store_config(eval_model="m", scan_batch_size=1),
        {},
        caller=caller,
    )
    assert len(saved) == 8
    assert caller.peak == 5
