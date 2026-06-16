import pytest
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


def test_visa_support():
    fields = ["Will you now or in the future require visa support to work in the role's location?"]
    r = pre_populate_answers(fields, PROFILE)
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
