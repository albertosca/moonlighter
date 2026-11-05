"""Scoring one job posting against the candidate profile with a single LLM call."""

import json
from typing import Any

from moonlighter.core.llm.anthropic_api import make_api_caller
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.spend_limit import is_spend_limit
from moonlighter.core.log import get_logger
from moonlighter.core.metrics import record_spend_limit_hit
from moonlighter.core.parsing import parse_llm_json
from moonlighter.discovery.evaluation.models import EvalInput, EvaluationResult
from moonlighter.discovery.evaluation.prompts import build_eval_prefix, eval_suffix
from moonlighter.discovery.evaluation.result_parsing import result_from

logger = get_logger(__name__)


async def evaluate_job(  # noqa: PLR0913, PLR0917 - public keyword API of service.py, scripts and tests; a parameter object would change every caller
    company: str,
    title: str,
    description: str,
    profile: dict[str, Any],
    model: str = "claude-sonnet-4-6",
    _caller: LLMCaller | None = None,
    *,
    # Required on purpose, even as None: an optional default let an ad-hoc caller
    # drop them silently and the regional filter degraded to the description
    # alone (2026-09-25 re-eval: 4 of 6 promoted jobs were false positives).
    location: str | None,
    remote_type: str | None,
) -> EvaluationResult:
    if _caller is None:
        _caller = make_api_caller()
    logger.debug("evaluating %s/%s", company, title)
    # Static prefix (profile + instructions) → cacheable; dynamic suffix = just the job.
    prefix = build_eval_prefix(profile)
    suffix = eval_suffix(EvalInput(company, title, description, location, remote_type))
    try:
        data = parse_llm_json(await _caller(suffix, model, cache_prefix=prefix))
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
