from candidatador.applicator.field_map import pre_populate_answers

PROFILE = {
    "name": "Maria de Souza Pereira",
    "phone": "11912345678",
    "email": "maria.pereira@example.com",
    "linkedin": "https://www.linkedin.com/in/mariapereira/",
    "location": "Belo Horizonte, MG, Brasil",
}


def test_first_name():
    r = pre_populate_answers(["First Name"], PROFILE)
    assert r["First Name"] == "Alberto"


def test_last_name():
    r = pre_populate_answers(["Last Name"], PROFILE)
    assert r["Last Name"] == "de Sá Cavalcanti de Albuquerque"


def test_preferred_name():
    r = pre_populate_answers(["Preferred First Name"], PROFILE)
    assert r["Preferred First Name"] == "Alberto"


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
    assert r["Location (City)"] == "Belo Horizonte"


def test_country():
    r = pre_populate_answers(["Country"], PROFILE)
    assert r["Country"] == "Brazil"


def test_visa_field_unknown_country_needs_review():
    fields = ["Will you now or in the future require visa support to work in the role's location?"]
    r = pre_populate_answers(fields, PROFILE)  # sem job_location → país desconhecido
    assert r[fields[0]] == "__NEEDS_REVIEW__"


def test_visa_field_brazil_location_answers_no():
    fields = ["Will you require visa sponsorship?"]
    r = pre_populate_answers(fields, PROFILE, job_location="São Paulo, Brazil")
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
    assert r["Where are you currently based?"] == "Belo Horizonte"


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
    assert r["Nome"] == "Alberto"


def test_ptbr_sobrenome_last_name():
    r = pre_populate_answers(["Sobrenome"], PROFILE)
    assert r["Sobrenome"] == "de Sá Cavalcanti de Albuquerque"


def test_ptbr_nome_de_preferencia():
    r = pre_populate_answers(["Nome de preferência"], PROFILE)
    assert r["Nome de preferência"] == "Alberto"


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
    assert r["Localização (Cidade)"] == "Belo Horizonte"


def test_ptbr_strips_asterisk():
    r = pre_populate_answers(["Telefone*", "Nome*", "Sobrenome*"], PROFILE)
    assert r["Telefone*"] == "11912345678"
    assert r["Nome*"] == "Alberto"
    assert r["Sobrenome*"] == "de Sá Cavalcanti de Albuquerque"


def test_currently_based_question_fills_city():
    """'Where are you currently based?' continua pré-populando a cidade."""
    r = pre_populate_answers(["Where are you currently based?"], PROFILE)
    assert r["Where are you currently based?"] == "Belo Horizonte"


def test_currently_based_midsentence_confirmation_not_prepopulated():
    """Campo de confirmação que CONTÉM 'currently based' no meio NÃO é tratado como
    cidade (deixa pro LLM responder 'Yes, I am aware')."""
    label = (
        "You are aware that this is a hybrid position and we require you to be "
        'currently based in one of the job post locations. Type "Yes, I am aware" if you confirm.'
    )
    r = pre_populate_answers([label], PROFILE)
    assert label not in r
