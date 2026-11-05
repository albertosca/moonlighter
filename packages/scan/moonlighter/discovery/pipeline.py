"""Evaluating and saving the jobs of one scan, in concurrent batches."""

import asyncio
from dataclasses import dataclass
from typing import Any, cast

from moonlighter.core.db import Job
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.spend_limit import is_spend_limit
from moonlighter.core.log import get_logger
from moonlighter.core.metrics import record_spend_limit_hit
from moonlighter.discovery.claims import release
from moonlighter.discovery.evaluation.batch import evaluate_jobs_batch
from moonlighter.discovery.evaluation.models import EvalInput
from moonlighter.discovery.evaluator_inputs import model_for
from moonlighter.discovery.no_eval import NO_EVAL, NoEval
from moonlighter.discovery.persistence import persist, scored_fields
from moonlighter.discovery.screening import (
    ScreeningRules,
    park_unevaluated,
    screen_chunk,
    screening_rules,
)
from moonlighter.discovery.sources.base import RawJob

logger = get_logger(__name__)


class _StopScan:
    """Sentinel returned by a coroutine that detected a spend limit and stopped."""


@dataclass(frozen=True)
class _Run:
    """What every chunk of one scan shares."""

    rules: ScreeningRules
    threshold: float
    model: str
    profile: dict[str, Any]
    caller: LLMCaller | NoEval
    stop: asyncio.Event
    semaphore: asyncio.Semaphore


def _eval_input(raw: RawJob) -> EvalInput:
    return EvalInput(
        raw.company,
        raw.title,
        raw.description or f"{raw.title} at {raw.company}",
        location=raw.location,
        remote_type=raw.remote_type,
    )


async def _score(run: _Run, saved: list[Job], to_evaluate: list[RawJob]) -> list[Job | _StopScan]:
    """Score the jobs the free checks left over and save them after the ones already saved."""
    try:
        evaluations = await evaluate_jobs_batch(
            [_eval_input(raw) for raw in to_evaluate],
            run.profile,
            run.model,
            caller=cast("LLMCaller", run.caller),
        )
    except Exception as error:
        for raw in to_evaluate:
            release(raw)
        if is_spend_limit(error):
            record_spend_limit_hit()
            run.stop.set()
        else:
            logger.exception("scan: unexpected error in batch — %s", error)  # noqa: TRY401 - the message text is pinned and carries the error
        # Returns results (jobs already persisted in this chunk) instead of
        # propagating — the raw exception would make gather() discard the
        # whole chunk from the report, undercounting jobs already saved in the DB.
        return [*saved, _StopScan()]

    scored = (
        persist(raw, **scored_fields(result, run.threshold))
        for raw, result in zip(to_evaluate, evaluations, strict=True)
    )
    return [*saved, *(job for job in scored if job is not None)]


async def _evaluate_chunk(run: _Run, chunk: list[RawJob]) -> list[Job | _StopScan]:
    async with run.semaphore:
        # Already stopped while waiting for the permit: don't reserve or call the LLM.
        if run.stop.is_set():
            return [_StopScan()]
        saved, to_evaluate = screen_chunk(chunk, run.rules)
        if not to_evaluate:
            return [*saved]
        if run.caller is NO_EVAL:
            return [*saved, *park_unevaluated(to_evaluate)]
        return await _score(run, saved, to_evaluate)


def _tally(outcomes: list[list[Job | _StopScan] | BaseException]) -> tuple[list[Job], bool]:
    saved: list[Job] = []
    stopped = False
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            logger.error("scan: batch failed — %s", outcome)
            stopped = True
            continue
        stopped = stopped or any(isinstance(item, _StopScan) for item in outcome)
        saved.extend(item for item in outcome if not isinstance(item, _StopScan))
    return saved, stopped


async def evaluate_and_store(
    new_jobs: list[RawJob],
    config: dict[str, Any],
    profile: dict[str, Any],
    *,
    caller: LLMCaller | NoEval,
) -> tuple[list[Job], bool]:
    """Evaluate and save jobs in concurrent BATCHES, stopping at the first spend limit or error.

    Up to scan_concurrency batches run in parallel, scan_batch_size jobs per
    batch. Returns the saved jobs and whether it stopped.
    """
    threshold = config["score_threshold"]
    run = _Run(
        rules=screening_rules(config, profile),
        threshold=threshold,
        model=model_for(config),
        profile=profile,
        caller=caller,
        stop=asyncio.Event(),
        semaphore=asyncio.Semaphore(config.get("scan_concurrency", 5)),
    )
    batch_size: int = config.get("scan_batch_size", 5)
    chunks = [new_jobs[start : start + batch_size] for start in range(0, len(new_jobs), batch_size)]
    outcomes = await asyncio.gather(
        *(_evaluate_chunk(run, chunk) for chunk in chunks), return_exceptions=True
    )
    saved, stopped = _tally(outcomes)
    if stopped:
        logger.warning("scan_and_evaluate: stopped by spend limit after %d jobs", len(saved))
    return saved, stopped
