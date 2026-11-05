"""The entry point: work authorization before the static rules, and what lands in the result."""

from moonlighter.application.answers.matching.field_map import pre_populate_answers
from tests.application.answers.candidate_profiles import PROFILE

WA_CONFIG_BRAZIL = {
    "work_authorization": {
        "citizenship_country": "brazil",
        "authorized_answer": "Yes",
        "not_authorized_answer": "No",
    }
}


def test_visa_field_unknown_country_needs_review():
    fields = ["Will you now or in the future require visa support to work in the role's location?"]
    result = pre_populate_answers(fields, PROFILE)  # no job_location → unknown country
    assert result[fields[0]] == "__NEEDS_REVIEW__"


def test_visa_field_brazil_location_answers_no():
    fields = ["Will you require visa sponsorship?"]
    result = pre_populate_answers(
        fields, PROFILE, config=WA_CONFIG_BRAZIL, job_location="São Paulo, Brazil"
    )
    assert result[fields[0]] == "No"


def test_unknown_field_not_included():
    result = pre_populate_answers(["Why do you want to work here?"], PROFILE)
    assert "Why do you want to work here?" not in result


def test_multiple_fields():
    fields = ["First Name", "Last Name", "Phone", "Email", "Why do you want to work here?"]
    result = pre_populate_answers(fields, PROFILE)
    assert len(result) == 4
    assert "Why do you want to work here?" not in result
