from gauntler.application.answers.field_map import pre_populate_answers

PROFILE = {
    "name": "Maria de Souza Pereira",
    "phone": "11912345678",
    "email": "maria.pereira@example.com",
    "linkedin": "https://www.linkedin.com/in/mariapereira/",
    "location": "São Paulo, SP, Brasil",
    # campos genéricos de localização/idioma/disponibilidade
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


def test_country():
    r = pre_populate_answers(["Country"], PROFILE)
    assert r["Country"] == "Brazil"


def test_visa_field_unknown_country_needs_review():
    fields = ["Will you now or in the future require visa support to work in the role's location?"]
    r = pre_populate_answers(fields, PROFILE)  # sem job_location → país desconhecido
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


# ── PT-BR labels (forms em português, ex: Nubank Investments) ──────────────────


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
    """'Where are you currently based?' continua pré-populando a cidade."""
    r = pre_populate_answers(["Where are you currently based?"], PROFILE)
    assert r["Where are you currently based?"] == "São Paulo"


def test_currently_based_midsentence_confirmation_not_prepopulated():
    """Campo de confirmação que CONTÉM 'currently based' no meio NÃO é tratado como
    cidade (deixa pro LLM responder 'Yes, I am aware')."""
    label = (
        "You are aware that this is a hybrid position and we require you to be "
        'currently based in one of the job post locations. Type "Yes, I am aware" if you confirm.'
    )
    r = pre_populate_answers([label], PROFILE)
    assert label not in r


# ── Campos opcionais do profile (country_en, country_pt, english_level, office_available) ──


PROFILE_NO_LOCALE = {
    "name": "Test User",
    "phone": "11999999999",
    "email": "test@example.com",
    "linkedin": "https://www.linkedin.com/in/testuser/",
    "location": "São Paulo, SP, Brazil",
}


def test_country_absent_from_profile_not_prepopulated():
    """Sem country_en no perfil → campo 'Country' não entra no resultado (LLM decide)."""
    r = pre_populate_answers(["Country"], PROFILE_NO_LOCALE)
    assert "Country" not in r


def test_pais_absent_from_profile_not_prepopulated():
    """Sem country_pt no perfil → campo 'País' não entra no resultado."""
    r = pre_populate_answers(["País"], PROFILE_NO_LOCALE)
    assert "País" not in r


def test_english_level_absent_from_profile_not_prepopulated():
    """Sem english_level no perfil → campo 'English level' não entra no resultado."""
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
    """Sem office_available no perfil → campo não entra no resultado."""
    r = pre_populate_answers(
        ["Are you able to work from the office at least two days per week?"], PROFILE_NO_LOCALE
    )
    assert "Are you able to work from the office at least two days per week?" not in r


def test_country_en_from_profile():
    """country_en no perfil → usado como resposta para ^country$."""
    profile = {**PROFILE_NO_LOCALE, "country_en": "Germany"}
    r = pre_populate_answers(["Country"], profile)
    assert r["Country"] == "Germany"


def test_english_level_from_profile():
    """english_level no perfil → usado na regra de proficiência."""
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
