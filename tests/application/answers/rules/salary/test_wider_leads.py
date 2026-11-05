"""The salary rule's wider leads: value words, bare PT-BR keywords and question-shaped labels."""

from moonlighter.application.answers.matching.field_map import pre_populate_answers
from moonlighter.application.answers.needs_review import NEEDS_REVIEW_SENTINEL
from moonlighter.application.answers.rules.static_rules import static_answer

# ── Salary Coverage E3 — wider lead words and bare PT keywords ──


class TestSalaryCoverageE3:
    """Coverage tests for salary auto-fill with additional lead words and PT-BR keywords."""

    @staticmethod
    def salary_profile():
        """Profile fixture with salary_target_brl_monthly for E3 tests."""
        return {"preferences": {"salary_target_brl_monthly": 25000}}

    # New: leading value words.
    def test_minimum_salary_fills(self):
        salary_profile = self.salary_profile()
        assert static_answer("Minimum salary", salary_profile) == "BRL 25.000/month"

    def test_base_compensation_fills(self):
        salary_profile = self.salary_profile()
        assert static_answer("Base compensation", salary_profile) == "BRL 25.000/month"

    def test_total_compensation_fills(self):
        salary_profile = self.salary_profile()
        assert static_answer("Total compensation", salary_profile) == "BRL 25.000/month"

    # New: bare PT keywords.
    def test_ptbr_bare_salario_fills(self):
        salary_profile = self.salary_profile()
        assert static_answer("Salário", salary_profile) == "BRL 25.000/month"

    def test_ptbr_faixa_salarial_fills(self):
        salary_profile = self.salary_profile()
        assert static_answer("Faixa salarial", salary_profile) == "BRL 25.000/month"

    # Invariant: essays starting with a keyword still fall through to the LLM.
    def test_ptbr_salario_essay_not_prepopulated(self):
        salary_profile = self.salary_profile()
        assert static_answer("Salário: conte sua história salarial", salary_profile) is None

    def test_minimum_salary_essay_not_prepopulated(self):
        salary_profile = self.salary_profile()
        assert static_answer("Minimum salary you would accept and why", salary_profile) is None


# ─── Question-shaped salary labels (the 2026-08-03 Holepunch gap) ────────────


def test_salary_question_with_foreign_units_refuses():
    """The REAL live label that fell through to the LLM. With the interrogative
    lead it now matches — and the currency/period guard refuses (annual USD
    against a BRL-monthly figure).
    """
    profile = {"preferences": {"salary_target_brl_monthly": 35000}}
    answers = pre_populate_answers(
        ["What is your expected salary? (annual USD)"],
        profile,
        {},
        job_location=None,
        job_remote_type=None,
    )
    assert answers["What is your expected salary? (annual USD)"] == NEEDS_REVIEW_SENTINEL


def test_salary_question_plain_answers_the_figure():
    profile = {"preferences": {"salary_target_brl_monthly": 35000}}
    answers = pre_populate_answers(
        ["What is your salary expectation?"], profile, {}, job_location=None, job_remote_type=None
    )
    assert answers["What is your salary expectation?"] == "BRL 35.000/month"


def test_salary_question_contracted_lead():
    profile = {"preferences": {"salary_target_brl_monthly": 35000}}
    answers = pre_populate_answers(
        ["What's your expected salary (BRL, monthly)?"],
        profile,
        {},
        job_location=None,
        job_remote_type=None,
    )
    assert answers["What's your expected salary (BRL, monthly)?"] == "BRL 35.000/month"


def test_salary_question_typographic_apostrophe():
    profile = {"preferences": {"salary_target_brl_monthly": 35000}}
    answers = pre_populate_answers(
        ["What’s your expected salary (BRL, monthly)?"],
        profile,
        {},
        job_location=None,
        job_remote_type=None,
    )
    assert answers["What’s your expected salary (BRL, monthly)?"] == "BRL 35.000/month"


def test_salary_question_ptbr_lead():
    profile = {"preferences": {"salary_target_brl_monthly": 35000}}
    answers = pre_populate_answers(
        ["Qual a sua pretensão salarial?"], profile, {}, job_location=None, job_remote_type=None
    )
    assert answers["Qual a sua pretensão salarial?"] == "BRL 35.000/month"


def test_salary_essay_with_interrogative_lead_still_falls_through():
    """The lead must not re-open the essay over-match: 'view on salary
    transparency' continues into non-whitelisted words and must reach the LLM.
    """
    profile = {"preferences": {"salary_target_brl_monthly": 35000}}
    answers = pre_populate_answers(
        ["What is your view on salary transparency?"],
        profile,
        {},
        job_location=None,
        job_remote_type=None,
    )
    assert "What is your view on salary transparency?" not in answers


def test_salary_growth_question_still_falls_through():
    profile = {"preferences": {"salary_target_brl_monthly": 35000}}
    answers = pre_populate_answers(
        ["What is your expected salary growth over five years?"],
        profile,
        {},
        job_location=None,
        job_remote_type=None,
    )
    assert "What is your expected salary growth over five years?" not in answers
