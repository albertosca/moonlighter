"""Scoring one job posting against the candidate profile with a single LLM call."""

import json
import logging
from typing import Any

from moonlighter.core.config.defaults import DEFAULT_LLM_MODEL
from moonlighter.core.llm.anthropic_api import make_api_caller
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.spend_limit import is_spend_limit
from moonlighter.core.metrics import record_spend_limit_hit
from moonlighter.core.parsing import parse_llm_json
from moonlighter.discovery.evaluation.models import EvalInput, EvaluationResult
from moonlighter.discovery.evaluation.prompts import build_eval_prefix, eval_suffix
from moonlighter.discovery.evaluation.result_parsing import result_from

logger = logging.getLogger(__name__)


async def evaluate_job(
    job: EvalInput,
    profile: dict[str, Any],
    *,
    model: str = DEFAULT_LLM_MODEL,
    caller: LLMCaller | None = None,
) -> EvaluationResult:
    if caller is None:
        caller = make_api_caller()
    company, title = job.company, job.title
    logger.debug("evaluating %s/%s", company, title)
    # Static prefix (profile + instructions) → cacheable; dynamic suffix = just the job.
    prefix = build_eval_prefix(profile)
    suffix = eval_suffix(job)
    try:
        data = parse_llm_json(await caller(suffix, model, cache_prefix=prefix))
        result = result_from(data)
        logger.debug("→ score %.1f (%s)", result.score, company)
    except json.JSONDecodeError:
        logger.warning("evaluator: parse error for %s/%s", company, title, exc_info=True)
        return EvaluationResult(score=0.0, score_notes="parse error: LLM returned non-JSON")
    except Exception as error:
        if is_spend_limit(error):
            record_spend_limit_hit()
            raise  # quota exhausted — the caller decides to stop; not the job's fault
        logger.warning("evaluator: error for %s/%s — %s", company, title, error, exc_info=True)
        return EvaluationResult(score=0.0, score_notes=f"evaluation error: {error}")
    else:
        return result
