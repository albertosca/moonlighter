"""Location rules: city, address and country, and where the candidate is based."""

from moonlighter.application.answers.field_map import pre_populate_answers

from tests.application.answers.candidate_profiles import PROFILE


def test_location_city():
    result = pre_populate_answers(["Location (City)"], PROFILE)
    assert result["Location (City)"] == "São Paulo"


def test_address():
    result = pre_populate_answers(["Address"], PROFILE)
    assert result["Address"] == "São Paulo, SP, Brasil"


def test_country():
    result = pre_populate_answers(["Country"], PROFILE)
    assert result["Country"] == "Brazil"


def test_currently_based():
    result = pre_populate_answers(["Where are you currently based?"], PROFILE)
    assert result["Where are you currently based?"] == "São Paulo"
