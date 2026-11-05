import logging

import pytest

from moonlighter.core.metrics import (
    LLMMetrics,
    operation_metrics,
    record_call,
    record_spend_limit_hit,
)


def test_record_call_accumulates_inside_scope():
    with operation_metrics("op") as metrics:
        record_call(1.5, input_tokens=10, output_tokens=20)
        record_call(0.5, input_tokens=3, output_tokens=4)
    assert metrics.calls == 2
    assert metrics.total_seconds == 2.0
    assert metrics.input_tokens == 13
    assert metrics.output_tokens == 24
    assert metrics.spend_limit_hits == 0


def test_record_spend_limit_hit_increments():
    with operation_metrics("op") as metrics:
        record_spend_limit_hit()
        record_spend_limit_hit()
    assert metrics.spend_limit_hits == 2


def test_record_call_without_scope_is_noop():
    # Must not raise when no operation scope is active (core/llm/ callers may run
    # outside any scope, e.g. in isolated unit tests).
    record_call(1.0, input_tokens=5)
    record_spend_limit_hit()


def test_scope_starts_fresh_each_time():
    with operation_metrics("a") as first:
        record_call(1.0)
    with operation_metrics("b") as second:
        record_call(2.0)
    assert first.calls == 1
    assert first.total_seconds == 1.0
    assert second.calls == 1
    assert second.total_seconds == 2.0
    assert first is not second


def test_summary_logged_once_on_exit(caplog):
    with caplog.at_level(logging.INFO), operation_metrics("scan_and_evaluate"):
        record_call(1.25, input_tokens=100, output_tokens=200)
    lines = [record for record in caplog.records if "scan_and_evaluate" in record.getMessage()]
    assert len(lines) == 1
    message = lines[0].getMessage()
    assert "calls=1" in message
    assert "spend_limit_hits=0" in message


def test_summary_logged_even_on_exception(caplog):
    with (  # noqa: PT012 - record_call(0.5) cannot raise; the raise must cross the scope's exit
        caplog.at_level(logging.INFO),
        pytest.raises(ValueError, match="boom"),
        operation_metrics("apply_jobs"),
    ):
        record_call(0.5)
        raise ValueError("boom")
    assert any("apply_jobs" in record.getMessage() for record in caplog.records)


def test_llmmetrics_defaults():
    metrics = LLMMetrics()
    assert (
        metrics.calls,
        metrics.total_seconds,
        metrics.input_tokens,
        metrics.output_tokens,
        metrics.spend_limit_hits,
    ) == (
        0,
        0.0,
        0,
        0,
        0,
    )
