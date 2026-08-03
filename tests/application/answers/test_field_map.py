from moonlighter.application.answers.field_map import _static_answer, pre_populate_answers
from moonlighter.core.config import NEEDS_REVIEW_SENTINEL

PROFILE = {
    "name": "Maria de Souza Pereira",
    "phone": "11912345678",
    "email": "maria.pereira@example.com",
    "linkedin": "https://www.linkedin.com/in/mariapereira/",
    "location": "São Paulo, SP, Brasil",
    # generic location/language/availability fields
    "country_en": "Brazil",
    "country_pt": "Brasil",
    "english_level": "Fluent",
    "office_available": True,
}

WA_CONFIG_BRAZIL = {
    "work_authorization": {
        "citizenship_country": "brazil",
        "authorized_answer": "Yes",
        "not_authorized_answer": "No",
    }
}


def test_first_name():
    r = pre_populate_answers(["First Name"], PROFILE)
    assert r["First Name"] == "Maria"


def test_last_name():
    r = pre_populate_answers(["Last Name"], PROFILE)
    assert r["Last Name"] == "de Souza Pereira"


def test_preferred_name():
    r = pre_populate_answers(["Preferred First Name"], PROFILE)
    assert r["Preferred First Name"] == "Maria"


def test_full_name():
    """A single "Full name" field is the norm outside the Greenhouse/Lever
    first+last convention. Without a rule it fell through to the LLM, which
    answered "full legal name is not present in the profile" -- leaving a
    required field blank on a real application (live Recruitee, 2026-08-03)."""
    r = pre_populate_answers(["Full name"], PROFILE)
    assert r["Full name"] == "Maria de Souza Pereira"


def test_full_name_variants():
    for label in ["Full Name *", "full name", "Your full name", "Nome completo"]:
        r = pre_populate_answers([label], PROFILE)
        assert r.get(label) == "Maria de Souza Pereira", f"{label!r} não preencheu"


def test_full_name_does_not_shadow_first_or_last():
    """The full-name rule must not swallow the first/last labels it sits near."""
    r = pre_populate_answers(["First Name", "Last Name"], PROFILE)
    assert r["First Name"] == "Maria"
    assert r["Last Name"] == "de Souza Pereira"


def test_phone():
    r = pre_populate_answers(["Phone"], PROFILE)
    assert r["Phone"] == "11912345678"


def test_email():
    r = pre_populate_answers(["Email"], PROFILE)
    assert r["Email"] == "maria.pereira@example.com"


def test_linkedin():
    r = pre_populate_answers(["LinkedIn Profile"], PROFILE)
    assert r["LinkedIn Profile"] == "https://www.linkedin.com/in/mariapereira/"


def test_location_city():
    r = pre_populate_answers(["Location (City)"], PROFILE)
    assert r["Location (City)"] == "São Paulo"


def test_address():
    r = pre_populate_answers(["Address"], PROFILE)
    assert r["Address"] == "São Paulo, SP, Brasil"


def test_country():
    r = pre_populate_answers(["Country"], PROFILE)
    assert r["Country"] == "Brazil"


def test_visa_field_unknown_country_needs_review():
    fields = ["Will you now or in the future require visa support to work in the role's location?"]
    r = pre_populate_answers(fields, PROFILE)  # no job_location → unknown country
    assert r[fields[0]] == "__NEEDS_REVIEW__"


def test_visa_field_brazil_location_answers_no():
    fields = ["Will you require visa sponsorship?"]
    r = pre_populate_answers(
        fields, PROFILE, config=WA_CONFIG_BRAZIL, job_location="São Paulo, Brazil"
    )
    assert r[fields[0]] == "No"


def test_office_availability():
    fields = ["Are you able to work from the office at least two days per week?"]
    r = pre_populate_answers(fields, PROFILE)
    assert r[fields[0]] == "Yes"


def test_english_level():
    r = pre_populate_answers(["English level"], PROFILE)
    assert r["English level"] == "Fluent"


def test_currently_based():
    r = pre_populate_answers(["Where are you currently based?"], PROFILE)
    assert r["Where are you currently based?"] == "São Paulo"


def test_unknown_field_not_included():
    r = pre_populate_answers(["Why do you want to work here?"], PROFILE)
    assert "Why do you want to work here?" not in r


def test_strips_asterisk_from_label():
    r = pre_populate_answers(["Phone *"], PROFILE)
    assert r["Phone *"] == "11912345678"


def test_empty_profile_phone_not_included():
    r = pre_populate_answers(["Phone"], {})
    assert "Phone" not in r


def test_multiple_fields():
    fields = ["First Name", "Last Name", "Phone", "Email", "Why do you want to work here?"]
    r = pre_populate_answers(fields, PROFILE)
    assert len(r) == 4
    assert "Why do you want to work here?" not in r


# ── PT-BR labels (Portuguese-language forms, e.g. Nubank Investments) ─────────


def test_ptbr_nome_first_name():
    r = pre_populate_answers(["Nome"], PROFILE)
    assert r["Nome"] == "Maria"


def test_ptbr_sobrenome_last_name():
    r = pre_populate_answers(["Sobrenome"], PROFILE)
    assert r["Sobrenome"] == "de Souza Pereira"


def test_ptbr_nome_de_preferencia():
    r = pre_populate_answers(["Nome de preferência"], PROFILE)
    assert r["Nome de preferência"] == "Maria"


def test_ptbr_email():
    r = pre_populate_answers(["E-mail"], PROFILE)
    assert r["E-mail"] == "maria.pereira@example.com"


def test_ptbr_telefone():
    r = pre_populate_answers(["Telefone"], PROFILE)
    assert r["Telefone"] == "11912345678"


def test_ptbr_pais_brasil():
    r = pre_populate_answers(["País"], PROFILE)
    assert r["País"] == "Brasil"


def test_ptbr_localizacao_cidade():
    r = pre_populate_answers(["Localização (Cidade)"], PROFILE)
    assert r["Localização (Cidade)"] == "São Paulo"


def test_ptbr_strips_asterisk():
    r = pre_populate_answers(["Telefone*", "Nome*", "Sobrenome*"], PROFILE)
    assert r["Telefone*"] == "11912345678"
    assert r["Nome*"] == "Maria"
    assert r["Sobrenome*"] == "de Souza Pereira"


def test_currently_based_question_fills_city():
    """'Where are you currently based?' keeps pre-populating the city."""
    r = pre_populate_answers(["Where are you currently based?"], PROFILE)
    assert r["Where are you currently based?"] == "São Paulo"


def test_currently_based_midsentence_confirmation_not_prepopulated():
    """A confirmation field that CONTAINS 'currently based' mid-sentence is NOT treated
    as the city (leaves it for the LLM to answer 'Yes, I am aware')."""
    label = (
        "You are aware that this is a hybrid position and we require you to be "
        'currently based in one of the job post locations. Type "Yes, I am aware" if you confirm.'
    )
    r = pre_populate_answers([label], PROFILE)
    assert label not in r


# ── Optional profile fields (country_en, country_pt, english_level, office_available) ─────


PROFILE_NO_LOCALE = {
    "name": "Test User",
    "phone": "11999999999",
    "email": "test@example.com",
    "linkedin": "https://www.linkedin.com/in/testuser/",
    "location": "São Paulo, SP, Brazil",
}


def test_country_absent_from_profile_not_prepopulated():
    """No country_en in the profile → 'Country' field doesn't enter the result (LLM decides)."""
    r = pre_populate_answers(["Country"], PROFILE_NO_LOCALE)
    assert "Country" not in r


def test_pais_absent_from_profile_not_prepopulated():
    """No country_pt in the profile → 'País' field doesn't enter the result."""
    r = pre_populate_answers(["País"], PROFILE_NO_LOCALE)
    assert "País" not in r


def test_english_level_absent_from_profile_not_prepopulated():
    """No english_level in the profile → 'English level' field doesn't enter the result."""
    r = pre_populate_answers(["English level"], PROFILE_NO_LOCALE)
    assert "English level" not in r


def test_office_available_true_returns_yes():
    """office_available=True → 'Yes'."""
    profile = {**PROFILE_NO_LOCALE, "office_available": True}
    r = pre_populate_answers(
        ["Are you able to work from the office at least two days per week?"], profile
    )
    assert r["Are you able to work from the office at least two days per week?"] == "Yes"


def test_office_available_false_returns_no():
    """office_available=False → 'No'."""
    profile = {**PROFILE_NO_LOCALE, "office_available": False}
    r = pre_populate_answers(
        ["Are you able to work from the office at least two days per week?"], profile
    )
    assert r["Are you able to work from the office at least two days per week?"] == "No"


def test_office_absent_from_profile_not_prepopulated():
    """No office_available in the profile → field doesn't enter the result."""
    r = pre_populate_answers(
        ["Are you able to work from the office at least two days per week?"], PROFILE_NO_LOCALE
    )
    assert "Are you able to work from the office at least two days per week?" not in r


def test_country_en_from_profile():
    """country_en in the profile → used as the answer for ^country$."""
    profile = {**PROFILE_NO_LOCALE, "country_en": "Germany"}
    r = pre_populate_answers(["Country"], profile)
    assert r["Country"] == "Germany"


def test_english_level_from_profile():
    """english_level in the profile → used in the proficiency rule."""
    profile = {**PROFILE_NO_LOCALE, "english_level": "Native"}
    r = pre_populate_answers(["English level"], profile)
    assert r["English level"] == "Native"


# ── Compensation (E2) — filled statically so the salary figure never reaches the LLM ──


def test_salary_field_filled_from_preferences():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Salary expectation"], profile)
    assert out["Salary expectation"] == "40000"


def test_compensation_field_matches_too():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Desired compensation"], profile)
    assert out["Desired compensation"] == "40000"


def test_salary_field_absent_preference_yields_empty():
    out = pre_populate_answers(["Salary expectation"], {})
    assert out["Salary expectation"] == ""


def test_expected_salary_matches():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Expected salary"], profile)
    assert out["Expected salary"] == "40000"


def test_expected_pay_matches():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Expected pay"], profile)
    assert out["Expected pay"] == "40000"


def test_compensation_alone_matches():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Compensation"], profile)
    assert out["Compensation"] == "40000"


def test_ptbr_pretensao_salarial_matches():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Pretensão salarial"], profile)
    assert out["Pretensão salarial"] == "40000"


def test_ptbr_remuneracao_matches():
    profile = {"preferences": {"salary_target_brl_monthly": 40000}}
    out = pre_populate_answers(["Remuneração"], profile)
    assert out["Remuneração"] == "40000"


def test_salary_transparency_essay_not_prepopulated():
    """Long interrogative label that merely mentions 'salary' mid-sentence must NOT
    be replaced by a bare number — it should fall through to the LLM."""
    label = "What is your view on salary transparency?"
    out = pre_populate_answers([label], {"preferences": {"salary_target_brl_monthly": 40000}})
    assert label not in out


def test_desired_pay_essay_not_prepopulated():
    """'desired ... pay' appears, but not as the leading 'desired pay' value label —
    this is an essay prompt and must be left for the LLM."""
    label = "Please describe your desired pay range and reasoning"
    out = pre_populate_answers([label], {"preferences": {"salary_target_brl_monthly": 40000}})
    assert label not in out


def test_salary_target_zero_yields_zero_string():
    """An explicit salary_target_brl_monthly of 0 must yield '0', not '' — 0 is a
    configured (if unusual) value, not 'unconfigured'."""
    out = pre_populate_answers(
        ["Salary expectation"], {"preferences": {"salary_target_brl_monthly": 0}}
    )
    assert out["Salary expectation"] == "0"


def test_salary_history_essay_not_prepopulated():
    """A label that *starts* with 'Salary' but continues into an essay ('history —
    describe...') is not a value question — filling it with the bare target number is
    silent degradation. It must fall through to the LLM."""
    label = "Salary history — describe your last 3 roles"
    out = pre_populate_answers([label], {"preferences": {"salary_target_brl_monthly": 40000}})
    assert label not in out


def test_compensation_philosophy_essay_not_prepopulated():
    """Same class, start-anchored on 'Compensation': 'Compensation philosophy: what
    motivates you?' is an essay prompt, not a compensation *value* field."""
    label = "Compensation philosophy: what motivates you?"
    out = pre_populate_answers([label], {"preferences": {"salary_target_brl_monthly": 40000}})
    assert label not in out


def test_salary_essay_hidden_in_parenthetical_not_prepopulated():
    """The trailing parenthetical is for short currency/period notes ('(BRL)'), not a
    place to smuggle an essay. A long parenthetical must not let an essay label through
    to the bare-number fill — the same silent-degradation class, via the paren vector."""
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
        assert out[label] == "40000"


def test_ptbr_pretensoes_salariais_plural_matches():
    """Plural 'Pretensões salariais' is as common a BR phrasing as the singular the
    docstring targets — the qualifier must accept the plural agreement form."""
    out = pre_populate_answers(
        ["Pretensões salariais"], {"preferences": {"salary_target_brl_monthly": 40000}}
    )
    assert out["Pretensões salariais"] == "40000"


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
        assert _static_answer("Minimum salary", salary_profile) == "25000"

    def test_base_compensation_fills(self):
        salary_profile = self.salary_profile()
        assert _static_answer("Base compensation", salary_profile) == "25000"

    def test_total_compensation_fills(self):
        salary_profile = self.salary_profile()
        assert _static_answer("Total compensation", salary_profile) == "25000"

    # New: bare PT keywords.
    def test_ptbr_bare_salario_fills(self):
        salary_profile = self.salary_profile()
        assert _static_answer("Salário", salary_profile) == "25000"

    def test_ptbr_faixa_salarial_fills(self):
        salary_profile = self.salary_profile()
        assert _static_answer("Faixa salarial", salary_profile) == "25000"

    # Invariant: essays starting with a keyword still fall through to the LLM.
    def test_ptbr_salario_essay_not_prepopulated(self):
        salary_profile = self.salary_profile()
        assert _static_answer("Salário: conte sua história salarial", salary_profile) is None

    def test_minimum_salary_essay_not_prepopulated(self):
        salary_profile = self.salary_profile()
        assert _static_answer("Minimum salary you would accept and why", salary_profile) is None


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
        assert out[label] == "35000", f"{label!r} deveria preencher"


def test_salary_still_fills_when_the_label_states_no_unit():
    """Unchanged behaviour: with nothing stated, the profile's own unit is the
    only assumption available, and it is the user's own stated target."""
    out = pre_populate_answers(["Expected salary"], _SALARY_PROFILE)
    assert out["Expected salary"] == "35000"


def test_salary_refusal_never_sends_the_field_to_the_llm():
    """E2: the figure must never reach the prompt. Refusing must therefore mean
    the sentinel (which is_skip treats as skip and the service reports as
    pending), never None -- None would let the LLM answer the salary question."""
    out = pre_populate_answers(["Expected salary (annual USD)"], _SALARY_PROFILE)
    assert "Expected salary (annual USD)" in out
