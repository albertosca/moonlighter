"""Tests for the evaluation input and result models."""

from dataclasses import FrozenInstanceError

import pytest

from moonlighter.discovery.evaluation.models import EvalInput


def test_eval_input_is_frozen():
    """EvalInput is a frozen dataclass."""
    inp = EvalInput(company="Acme", title="Engineer", description="desc")
    with pytest.raises(FrozenInstanceError):
        inp.company = "other"


def test_eval_input_fields():
    """EvalInput tem os campos esperados."""
    inp = EvalInput(company="Acme", title="Sr Engineer", description="Build stuff.")
    assert inp.company == "Acme"
    assert inp.title == "Sr Engineer"
    assert inp.description == "Build stuff."
