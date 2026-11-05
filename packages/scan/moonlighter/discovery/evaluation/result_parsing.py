"""Turning the model's reply into validated EvaluationResult values, never trusting its types."""

import json
import math
from typing import Any

from moonlighter.core.parsing import parse_llm_json
from moonlighter.discovery.evaluation.models import EvaluationResult


def result_from(data: dict[str, Any]) -> EvaluationResult:
    caveats = data.get("caveats")
    return EvaluationResult(
        score=_as_float(data.get("score")),
        score_notes=str(data.get("score_notes") or ""),
        caveats=caveats if isinstance(caveats, list) else [],
        salary_min=_as_salary(data.get("salary_min")),
        salary_max=_as_salary(data.get("salary_max")),
        salary_currency=_as_salary_currency(data.get("salary_currency")),
        salary_source=_as_salary_source(data.get("salary_source")),
    )


def _as_float(value: Any) -> float:
    """Coerce the score to float and clamp it to [0.0, 10.0] (S-05).

    Invalid, out-of-range, or non-finite values (NaN/inf — including strings like
    "Infinity"/"NaN", which float() accepts) become 0.0. We never let a value
    produced from untrusted text (the job posting) decide on its own where
    the listing lands in the ranking.
    """
    try:
        score = float(value)
    except TypeError, ValueError:
        return 0.0
    if not math.isfinite(score):
        return 0.0
    return max(0.0, min(10.0, score))


_VALID_SALARY_SOURCES = {"stated", "llm_estimate"}


def _as_salary(value: Any) -> int | None:
    """Salary from the LLM: only a non-negative int (or a float with an integer value).

    Never a bool (a subclass of int in Python) — anything else becomes None
    (S-05, we never trust text/negatives in an IntegerField column).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        return int(value) if value >= 0 else None
    return None


def _as_salary_currency(value: Any) -> str | None:
    """Normalize salary_currency: only a non-empty string, capped at 10 chars."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:10]


def _as_salary_source(value: Any) -> str | None:
    """Strict whitelist — any value outside the known set becomes None."""
    return value if isinstance(value, str) and value in _VALID_SALARY_SOURCES else None


def parse_batch(raw: str, expected_count: int) -> list[EvaluationResult] | None:
    """Parses the batch response into an array of expected_count EvaluationResult.

    Returns None when the STRUCTURE is invalid (not a list or size ≠ expected_count) — the caller
    then falls back to the per-job path. A malformed individual item is tolerated via result_from.
    """
    try:
        # Tries direct parsing (bare arrays); if that fails, tries extracting JSON from markdown/prose
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = parse_llm_json(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list) or len(data) != expected_count:
        return None
    return [result_from(item if isinstance(item, dict) else {}) for item in data]
