"""The salary rule: which labels it claims, and what it answers in the profile's units."""

from moonlighter.application.answers.field_map import pre_populate_answers


def test_salary_answer_separates_every_thousands_group_with_a_dot():
    profile = {"preferences": {"salary_target_brl_monthly": 1234567}}
    out = pre_populate_answers(["Salary expectation"], profile)
    assert out["Salary expectation"] == "BRL 1.234.567/month"
