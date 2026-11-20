"""Tests for the evaluation input and result models."""

from dataclasses import FrozenInstanceError

import pytest

from moonlighter.discovery.evaluation.models import EvalInput


def test_eval_input_is_frozen():
    """EvalInput is a frozen dataclass."""
    inp = EvalInput(
        company="Acme", title="Engineer", description="desc", location=None, remote_type=None
    )
    with pytest.raises(FrozenInstanceError):
        inp.company = "other"


def test_eval_input_fields():
    """EvalInput has the expected fields."""
    inp = EvalInput(
        company="Acme",
        title="Sr Engineer",
        description="Build stuff.",
        location=None,
        remote_type=None,
    )
    assert inp.company == "Acme"
    assert inp.title == "Sr Engineer"
    assert inp.description == "Build stuff."


def test_eval_input_requires_location_and_remote_type():
    """Optional defaults let a caller drop them silently (2026-09-25 re-eval: 4 of 6
    promoted jobs were false positives). A caller must now say None on purpose.
    """
    with pytest.raises(TypeError, match="location"):
        EvalInput("Co", "Eng", "desc")  # type: ignore[call-arg]  # the omission under test


def test_eval_input_takes_location_and_remote_type_only_by_name():
    """By name only, so a swapped pair of strings cannot land in the wrong field."""
    with pytest.raises(TypeError):
        EvalInput("Co", "Eng", "desc", "Lisbon", "remote")  # type: ignore[call-arg]  # positional on purpose
