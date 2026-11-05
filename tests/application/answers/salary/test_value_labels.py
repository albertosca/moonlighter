"""Which labels the salary rule claims: short value questions, never essays that start with the keyword."""

from moonlighter.application.answers.field_map import pre_populate_answers

# ── Compensation (E2) — filled statically so the salary figure never reaches the LLM ──


def test_compensation_field_matches_too():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Desired compensation"], profile)
    assert out["Desired compensation"] == "BRL 40.000/month"


def test_expected_salary_matches():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Expected salary"], profile)
    assert out["Expected salary"] == "BRL 40.000/month"


def test_expected_pay_matches():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Expected pay"], profile)
    assert out["Expected pay"] == "BRL 40.000/month"


def test_compensation_alone_matches():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Compensation"], profile)
    assert out["Compensation"] == "BRL 40.000/month"


def test_ptbr_pretensao_salarial_matches():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Pretensão salarial"], profile)
    assert out["Pretensão salarial"] == "BRL 40.000/month"


def test_ptbr_remuneracao_matches():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Remuneração"], profile)
    assert out["Remuneração"] == "BRL 40.000/month"


def test_salary_transparency_essay_not_prepopulated():
    """Long interrogative label that merely mentions 'salary' mid-sentence must NOT
    be replaced by a salary figure — it should fall through to the LLM.
    """
    label = "What is your view on salary transparency?"
    out = pre_populate_answers([label], {"preferences": {"salary_target_brl_monthly": 40000}})
    assert label not in out


def test_desired_pay_essay_not_prepopulated():
    """'desired ... pay' appears, but not as the leading 'desired pay' value label —
    this is an essay prompt and must be left for the LLM.
    """
    label = "Please describe your desired pay range and reasoning"
    out = pre_populate_answers([label], {"preferences": {"salary_target_brl_monthly": 40000}})
    assert label not in out


def test_salary_history_essay_not_prepopulated():
    """A label that *starts* with 'Salary' but continues into an essay ('history —
    describe...') is not a value question — filling it with the bare target number is
    silent degradation. It must fall through to the LLM.
    """
    label = "Salary history — describe your last 3 roles"
    out = pre_populate_answers([label], {"preferences": {"salary_target_brl_monthly": 40000}})
    assert label not in out


def test_compensation_philosophy_essay_not_prepopulated():
    """Same class, start-anchored on 'Compensation': 'Compensation philosophy: what
    motivates you?' is an essay prompt, not a compensation *value* field.
    """
    label = "Compensation philosophy: what motivates you?"
    out = pre_populate_answers([label], {"preferences": {"salary_target_brl_monthly": 40000}})
    assert label not in out


def test_salary_essay_hidden_in_parenthetical_not_prepopulated():
    """The trailing parenthetical is for short currency/period notes ('(BRL)'), not a
    place to smuggle an essay. A long parenthetical must not let an essay label through
    to the bare-number fill — the same silent-degradation class, via the paren vector.
    """
    prof = {"preferences": {"salary_target_brl_monthly": 40000}}
    for label in (
        "Salary (please describe your history and reasoning in detail)",
        "Compensation (explain your philosophy and past negotiations)",
    ):
        out = pre_populate_answers([label], prof)
        assert label not in out


def test_salary_short_currency_parenthetical_still_prepopulated():
    """The legitimate short-note case must keep working after bounding the paren."""
    prof = {"preferences": {"salary_target_brl_monthly": 40000}}
    for label in ("Salary expectation (BRL)", "Salary (BRL)", "Salary (monthly)"):
        out = pre_populate_answers([label], prof)
        assert out[label] == "BRL 40.000/month"


def test_ptbr_pretensoes_salariais_plural_matches():
    """Plural 'Pretensões salariais' is as common a BR phrasing as the singular the
    docstring targets — the qualifier must accept the plural agreement form.
    """
    out = pre_populate_answers(
        ["Pretensões salariais"], {"preferences": {"salary_target_brl_monthly": 40000}}
    )
    assert out["Pretensões salariais"] == "BRL 40.000/month"
