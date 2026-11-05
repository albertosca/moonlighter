"""Tests for the coercions that sanitise each field of a model reply."""

from moonlighter.discovery.evaluation.result_parsing import (
    _as_float,
    _as_salary,
    _as_salary_currency,
    _as_salary_source,
)


def test_as_float_none_becomes_zero():
    assert _as_float(None) == 0.0


def test_as_float_non_numeric_string_becomes_zero():
    assert _as_float("high") == 0.0


def test_as_float_numeric_string_with_trailing_junk_becomes_zero():
    assert _as_float("5abc") == 0.0


def test_as_float_dict_becomes_zero():
    """float(dict) raises TypeError, not ValueError — both must be caught."""
    assert _as_float({"score": 9}) == 0.0


def test_as_float_list_becomes_zero():
    assert _as_float([1, 2]) == 0.0


def test_as_float_nan_string_becomes_zero():
    """float() accepts "NaN" as a string; math.isfinite rejects it (S-05)."""
    assert _as_float("NaN") == 0.0


def test_as_float_nan_object_becomes_zero():
    assert _as_float(float("nan")) == 0.0


def test_as_float_infinity_string_becomes_zero():
    assert _as_float("Infinity") == 0.0


def test_as_float_negative_infinity_becomes_zero():
    assert _as_float(float("-inf")) == 0.0


def test_as_float_negative_value_clamps_to_zero():
    assert _as_float(-5.0) == 0.0


def test_as_float_very_large_value_clamps_to_ten():
    assert _as_float(1e300) == 10.0


def test_as_float_valid_numeric_string_is_coerced():
    assert _as_float("7.5") == 7.5


def test_as_float_bool_true_is_coerced_like_int():
    """A bool is an int subclass; _as_float doesn't special-case it (unlike
    _as_salary, which explicitly rejects bools) — documents actual behavior.
    """
    assert _as_float(True) == 1.0  # noqa: FBT003 - the bool is the value under test


def test_as_salary_none_becomes_none():
    assert _as_salary(None) is None


def test_as_salary_bool_true_becomes_none():
    """A bool is a subclass of int in Python — must be rejected explicitly."""
    assert _as_salary(True) is None  # noqa: FBT003 - the bool is the value under test


def test_as_salary_bool_false_becomes_none():
    assert _as_salary(False) is None  # noqa: FBT003 - the bool is the value under test


def test_as_salary_negative_int_becomes_none():
    assert _as_salary(-1000) is None


def test_as_salary_negative_float_becomes_none():
    assert _as_salary(-1000.0) is None


def test_as_salary_non_integer_float_becomes_none():
    assert _as_salary(50000.5) is None


def test_as_salary_string_becomes_none():
    assert _as_salary("50000") is None


def test_as_salary_zero_is_valid():
    assert _as_salary(0) == 0


def test_as_salary_integer_valued_float_is_coerced():
    assert _as_salary(180000.0) == 180000


def test_as_salary_currency_none_becomes_none():
    assert _as_salary_currency(None) is None


def test_as_salary_currency_empty_string_becomes_none():
    assert _as_salary_currency("") is None


def test_as_salary_currency_whitespace_only_becomes_none():
    assert _as_salary_currency("   ") is None


def test_as_salary_currency_non_string_becomes_none():
    assert _as_salary_currency(42) is None


def test_as_salary_currency_is_stripped_and_capped_at_ten_chars():
    assert _as_salary_currency("  ABCDEFGHIJKLMNOP  ") == "ABCDEFGHIJ"


def test_as_salary_source_valid_stated():
    assert _as_salary_source("stated") == "stated"


def test_as_salary_source_valid_llm_estimate():
    assert _as_salary_source("llm_estimate") == "llm_estimate"


def test_as_salary_source_outside_closed_set_becomes_none():
    assert _as_salary_source("confirmed") is None


def test_as_salary_source_wrong_case_becomes_none():
    """Whitelist matching is case-sensitive — documents actual behavior."""
    assert _as_salary_source("Stated") is None


def test_as_salary_source_non_string_becomes_none():
    assert _as_salary_source(1) is None


def test_as_salary_source_none_becomes_none():
    assert _as_salary_source(None) is None
