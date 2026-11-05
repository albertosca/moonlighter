"""Runs one re-evaluation batch: filters titles, evaluates the rest concurrently and prints what happened.

A spend limit stops every job that has not yet reached the evaluator; jobs already in flight finish.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from moonlighter.core.db import Job
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.dispatch import make_caller
from moonlighter.core.llm.spend_limit import is_spend_limit
from moonlighter.core.metrics import operation_metrics
from moonlighter.discovery.evaluation.models import EvaluationResult
from moonlighter.discovery.evaluation.single import evaluate_job
from moonlighter.discovery.evaluation.title_filter import should_skip_by_title

from reevaluation_records import record_error, record_result, record_title_skip


@dataclass(frozen=True)
class ReevaluationSettings:
    """What a batch needs besides the jobs and the config: the resolved model and the run's switches."""

    model: str
    profile: dict[str, Any]
    threshold: float
    title_blocklist: list[str]
    dry_run: bool
    title_only: bool
    concurrency: int


@dataclass
class Tally:
    """Counts of what happened to the jobs in a batch."""

    skipped_by_title: int = 0
    promoted: int = 0
    stayed_archived: int = 0
    errors: int = 0
    stopped_by_spend_limit: bool = False


class _Batch:
    """The state of one run, with one method per step a job goes through."""

    def __init__(self, caller: LLMCaller, total: int, settings: ReevaluationSettings) -> None:
        self.caller = caller
        self.total = total
        self.settings = settings
        self.tally = Tally()
        self.semaphore = asyncio.Semaphore(settings.concurrency)
        self.stop = asyncio.Event()

    async def process(self, position: int, job: Job) -> None:
        label = f"[{position:4d}/{self.total}] [{job.company}] {job.title[:55]:55s}"
        matched_pattern = should_skip_by_title(job.title, self.settings.title_blocklist)
        if matched_pattern:
            self._skip_by_title(label, job, matched_pattern)
            return
        if self.stop.is_set():
            return
        async with self.semaphore:
            if not self.stop.is_set():
                await self._evaluate(label, job)

    def _skip_by_title(self, label: str, job: Job, matched_pattern: str) -> None:
        if not self.settings.dry_run:
            record_title_skip(job.id, matched_pattern)
        print(f"{label} -- skip title ({matched_pattern!r})")
        self.tally.skipped_by_title += 1

    async def _evaluate(self, label: str, job: Job) -> None:
        try:
            result = await self._call_evaluator(job)
        except Exception as error:  # noqa: BLE001 - any evaluator failure is reported per job, never fatal to the batch
            self._fail(label, job, error)
            return
        self._succeed(label, job, result)

    async def _call_evaluator(self, job: Job) -> EvaluationResult:
        if self.settings.title_only:
            description = job.title
        else:
            description = job.description or f"{job.title} at {job.company}"
        return await evaluate_job(
            company=job.company,
            title=job.title,
            description=description,
            profile=self.settings.profile,
            model=self.settings.model,
            _caller=self.caller,
            location=job.location,
            remote_type=job.remote_type,
        )

    def _fail(self, label: str, job: Job, error: Exception) -> None:
        if is_spend_limit(error):
            self.stop.set()
            self.tally.stopped_by_spend_limit = True
            print(f"{label} 🚫 SPEND LIMIT reached — stopping. Error: {error}")
            return
        print(f"{label} ✗ ERROR: {error}")
        self.tally.errors += 1
        if not self.settings.dry_run:
            record_error(job.id, error)

    def _succeed(self, label: str, job: Job, result: EvaluationResult) -> None:
        promoted = result.score >= self.settings.threshold
        status = "new" if promoted else "archived"
        icon = "↑ NEW" if promoted else "  arq"
        print(f"{label} {icon} score={result.score:.1f}")
        if not self.settings.dry_run:
            record_result(job.id, result, status)
        if promoted:
            self.tally.promoted += 1
        else:
            self.tally.stayed_archived += 1

    def print_summary(self) -> None:
        tally = self.tally
        settings = self.settings
        if tally.stopped_by_spend_limit:
            print("\n🚫 Re-evaluation interrupted by spend limit.")
        mode = "title-only" if settings.title_only else "full description"
        prefix = "[DRY RUN] " if settings.dry_run else ""
        print(
            f"\n{prefix}Result: {self.total} jobs found  [{mode}] concurrency={settings.concurrency}"
        )
        print(f"  -- skipped by title:       {tally.skipped_by_title}")
        print(f"  ↑ promoted to 'new':       {tally.promoted}")
        print(f"     remain archived:        {tally.stayed_archived}")
        print(f"  ✗ errors:                  {tally.errors}")
        print(f"  LLM calls ({settings.model}):      {self.total - tally.skipped_by_title}")


async def reevaluate(
    jobs: list[Job], config: dict[str, Any], settings: ReevaluationSettings
) -> None:
    """Evaluates every job concurrently, writes the outcomes unless it is a dry run, and prints a summary."""
    with operation_metrics("reevaluate"):
        batch = _Batch(make_caller(config), len(jobs), settings)
        await asyncio.gather(
            *[batch.process(position, job) for position, job in enumerate(jobs, 1)]
        )
        batch.print_summary()
