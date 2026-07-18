import logging

import pytest
from gauntler.core.metrics import (
    LLMMetrics,
    operation_metrics,
    record_call,
    record_spend_limit_hit,
)


def test_record_call_accumulates_inside_scope():
    with operation_metrics("op") as m:
        record_call(1.5, input_tokens=10, output_tokens=20)
        record_call(0.5, input_tokens=3, output_tokens=4)
    assert m.calls == 2
    assert m.total_seconds == 2.0
    assert m.input_tokens == 13
    assert m.output_tokens == 24
    assert m.spend_limit_hits == 0


def test_record_spend_limit_hit_increments():
    with operation_metrics("op") as m:
        record_spend_limit_hit()
        record_spend_limit_hit()
    assert m.spend_limit_hits == 2


def test_record_call_without_scope_is_noop():
    # Must not raise when no operation scope is active (llm.py callers may run
    # outside any scope, e.g. in isolated unit tests).
    record_call(1.0, input_tokens=5)
    record_spend_limit_hit()


def test_scope_starts_fresh_each_time():
    with operation_metrics("a") as first:
        record_call(1.0)
    with operation_metrics("b") as second:
        record_call(2.0)
    assert first.calls == 1 and first.total_seconds == 1.0
    assert second.calls == 1 and second.total_seconds == 2.0
    assert first is not second


def test_summary_logged_once_on_exit(caplog):
    with caplog.at_level(logging.INFO), operation_metrics("scan_and_evaluate"):
        record_call(1.25, input_tokens=100, output_tokens=200)
    lines = [r for r in caplog.records if "scan_and_evaluate" in r.getMessage()]
    assert len(lines) == 1
    msg = lines[0].getMessage()
    assert "calls=1" in msg
    assert "spend_limit_hits=0" in msg


def test_summary_logged_even_on_exception(caplog):
    with (
        caplog.at_level(logging.INFO),
        pytest.raises(ValueError),
        operation_metrics("apply_jobs"),
    ):
        record_call(0.5)
        raise ValueError("boom")
    assert any("apply_jobs" in r.getMessage() for r in caplog.records)


def test_llmmetrics_defaults():
    m = LLMMetrics()
    assert (m.calls, m.total_seconds, m.input_tokens, m.output_tokens, m.spend_limit_hits) == (
        0,
        0.0,
        0,
        0,
        0,
    )
