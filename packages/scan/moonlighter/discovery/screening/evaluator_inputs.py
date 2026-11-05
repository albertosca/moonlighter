"""What the evaluator needs before it can score a posting: a model and a real description."""

from typing import Any

from moonlighter.core.config.defaults import DEFAULT_EVAL_MODEL

MINIMUM_DESCRIPTION_LENGTH = 30


def model_for(config: dict[str, Any]) -> str:
    """The model a scan or a manual job is scored with: `eval_model`, then `llm_model`."""
    model: str = config.get("eval_model", config.get("llm_model", DEFAULT_EVAL_MODEL))
    return model


def is_description_insufficient(description: str | None) -> bool:
    """True when there isn't enough text to evaluate honestly.

    The scanner couldn't fetch a real description (e.g. InHire has no per-job
    detail endpoint, verified 2026-08-18). These jobs skip the LLM and wait for
    a human to paste the real page instead of scoring a guess.
    """
    return not description or len(description.strip()) < MINIMUM_DESCRIPTION_LENGTH
