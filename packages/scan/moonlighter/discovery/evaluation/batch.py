"""Scoring several job postings in one LLM call, falling back to one call per job."""

from typing import Any

from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.spend_limit import is_spend_limit
from moonlighter.core.log import get_logger
from moonlighter.core.metrics import record_spend_limit_hit
from moonlighter.discovery.evaluation.models import EvalInput, EvaluationResult
from moonlighter.discovery.evaluation.prompts import build_batch_prefix, jobs_block
from moonlighter.discovery.evaluation.result_parsing import parse_batch
from moonlighter.discovery.evaluation.single import evaluate_job

logger = get_logger(__name__)


async def _eval_each(
    jobs: list[EvalInput], profile: dict[str, Any], model: str, *, caller: LLMCaller
) -> list[EvaluationResult]:
    """Fallback: evaluates job by job (sequentially). A spend-limit in any of them propagates."""
    return [
        await evaluate_job(
            job.company,
            job.title,
            job.description,
            profile,
            model,
            caller,
            location=job.location,
            remote_type=job.remote_type,
        )
        for job in jobs
    ]


async def evaluate_jobs_batch(
    jobs: list[EvalInput], profile: dict[str, Any], model: str, *, caller: LLMCaller
) -> list[EvaluationResult]:
    """Evaluates K jobs in a single LLM call (profile sent once).

    On invalid parse or a non-quota error, falls back to the per-job path — never worsens
    robustness. A spend-limit propagates to the caller so it can stop the scan.
    """
    if len(jobs) == 1:
        return await _eval_each(jobs, profile, model, caller=caller)

    # Static prefix (profile + instructions, without the jobs) → cacheable.
    # Dynamic suffix = the jobs block (changes every batch).
    prefix = build_batch_prefix(profile, len(jobs))
    suffix = jobs_block(jobs)
    try:
        raw = await caller(suffix, model, cache_prefix=prefix)
    except Exception as error:
        if is_spend_limit(error):
            record_spend_limit_hit()
            raise
        logger.warning("batch eval: call error — fallback per-job: %s", error, exc_info=True)
        return await _eval_each(jobs, profile, model, caller=caller)

    parsed = parse_batch(raw, len(jobs))
    if parsed is None:
        logger.warning("batch eval: invalid parse — fallback per-job (%d jobs)", len(jobs))
        return await _eval_each(jobs, profile, model, caller=caller)
    return parsed
