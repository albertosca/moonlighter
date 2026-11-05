"""What the salary rule answers: the configured target in BRL per month, or a review marker."""

from moonlighter.application.answers.field_map import pre_populate_answers
from moonlighter.application.answers.needs_review import NEEDS_REVIEW_SENTINEL


def test_salary_field_filled_from_preferences():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Salary expectation"], profile)
    assert out["Salary expectation"] == "BRL 40.000/month"


def test_salary_field_absent_preference_yields_empty():
    out = pre_populate_answers(["Salary expectation"], {})
    assert out["Salary expectation"] == ""


def test_salary_target_zero_yields_zero_string():
    """An explicit salary_target_brl_monthly of 0 must yield a formatted 0, not ''
    — 0 is a configured (if unusual) value, not 'unconfigured'."""
    out = pre_populate_answers(
        ["Salary expectation"], {"preferences": {"salary_target_brl_monthly": 0}}
    )
    assert out["Salary expectation"] == "BRL 0/month"


def test_salary_answer_formats_thousands_with_dots():
    """The answer follows the format ATS labels themselves exemplify ("MXN 9.000"):
    currency code + dot-separated thousands + explicit period. A bare "35000" left
    the currency and period to the reader's guess — observed live on the Nubank
    form (2026-08-13), whose label asked "Currency + Monthly Salary" outright."""
    profile = {"preferences": {"salary_target_brl_monthly": 9500}}
    out = pre_populate_answers(["Salary expectation"], profile)
    assert out["Salary expectation"] == "BRL 9.500/month"


def test_salary_answer_separates_every_thousands_group_with_a_dot():
    profile = {"preferences": {"salary_target_brl_monthly": 1234567}}
    out = pre_populate_answers(["Salary expectation"], profile)
    assert out["Salary expectation"] == "BRL 1.234.567/month"


# ── Compensation: currency and period must match what the label asks for ──────


_SALARY_PROFILE = {"preferences": {"salary_target_brl_monthly": 35000}}


def test_salary_refuses_when_the_label_asks_for_a_foreign_currency():
    """The stored figure is BRL *per month*. Dropped into a field asking for
    annual USD it reads as $35,000/year -- wrong currency and ~2.4x under the
    intended number, in the one field where a wrong value is a concrete loss.
    Probed on a live Recruitee posting (2026-08-03)."""
    out = pre_populate_answers(["Expected salary (annual USD)"], _SALARY_PROFILE)
    assert out["Expected salary (annual USD)"] == NEEDS_REVIEW_SENTINEL


def test_salary_refuses_when_the_label_asks_for_a_different_period():
    out = pre_populate_answers(["Expected salary (annual)"], _SALARY_PROFILE)
    assert out["Expected salary (annual)"] == NEEDS_REVIEW_SENTINEL


def test_salary_refuses_for_ptbr_annual_labels():
    out = pre_populate_answers(["Pretensão salarial anual"], _SALARY_PROFILE)
    assert out["Pretensão salarial anual"] == NEEDS_REVIEW_SENTINEL


def test_salary_fills_when_the_label_agrees_with_the_stored_unit():
    for label in ["Expected salary (BRL)", "Pretensão salarial mensal", "Salary (monthly)"]:
        out = pre_populate_answers([label], _SALARY_PROFILE)
        assert out[label] == "BRL 35.000/month", f"{label!r} should be filled"


def test_salary_still_fills_when_the_label_states_no_unit():
    """Unchanged behaviour: with nothing stated, the profile's own unit is the
    only assumption available, and it is the user's own stated target."""
    out = pre_populate_answers(["Expected salary"], _SALARY_PROFILE)
    assert out["Expected salary"] == "BRL 35.000/month"


def test_salary_refusal_never_sends_the_field_to_the_llm():
    """E2: the figure must never reach the prompt. Refusing must therefore mean
    the sentinel (which the composer turns into a gap and the service reports as
    pending), never None -- None would let the LLM answer the salary question."""
    out = pre_populate_answers(["Expected salary (annual USD)"], _SALARY_PROFILE)
    assert "Expected salary (annual USD)" in out
