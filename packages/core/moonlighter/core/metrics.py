"""Per-operation LLM observability.

An `operation_metrics(name)` scope collects counters for all LLM calls made
inside it — including calls in child asyncio tasks, since asyncio copies the
context at task creation and every recorder mutates the SAME LLMMetrics object
the scope installed (no ContextVar reassignment). asyncio is single-threaded
and the recorders contain no `await`, so increments between await points are
atomic. Recorders are no-ops outside any scope, so the LLM callers never
require a scope to run.

Constraint: the CLI backend (the claude.ai subscription — this project's real
backend) exposes no token usage, so its summaries carry input_tokens=0/
output_tokens=0 and are meaningful only for calls/total_seconds/
spend_limit_hits. Token counts are real only on the API backend.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from moonlighter.core.log import get_logger

logger = get_logger(__name__)

_current: ContextVar[LLMMetrics | None] = ContextVar("llm_metrics", default=None)


@dataclass
class LLMMetrics:
    calls: int = 0
    total_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    spend_limit_hits: int = 0


@contextmanager
def operation_metrics(name: str) -> Iterator[LLMMetrics]:
    metrics = LLMMetrics()
    token = _current.set(metrics)
    try:
        yield metrics
    finally:
        _current.reset(token)
        logger.info(
            "op=%s calls=%d total_seconds=%.3f input_tokens=%d output_tokens=%d spend_limit_hits=%d",
            name,
            metrics.calls,
            metrics.total_seconds,
            metrics.input_tokens,
            metrics.output_tokens,
            metrics.spend_limit_hits,
        )


def record_call(seconds: float, input_tokens: int = 0, output_tokens: int = 0) -> None:
    metrics = _current.get()
    if metrics is None:
        return
    metrics.calls += 1
    metrics.total_seconds += seconds
    metrics.input_tokens += input_tokens
    metrics.output_tokens += output_tokens


def record_spend_limit_hit() -> None:
    metrics = _current.get()
    if metrics is None:
        return
    metrics.spend_limit_hits += 1
