"""Optional profile fields: answered when the profile holds them, left to the LLM when not."""

from moonlighter.application.answers.matching.field_map import pre_populate_answers

from tests.application.answers.candidate_profiles import PROFILE


def test_office_availability():
    fields = ["Are you able to work from the office at least two days per week?"]
    result = pre_populate_answers(fields, PROFILE)
    assert result[fields[0]] == "Yes"


def test_english_level():
    result = pre_populate_answers(["English level"], PROFILE)
    assert result["English level"] == "Fluent"


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
    result = pre_populate_answers(["Country"], PROFILE_NO_LOCALE)
    assert "Country" not in result


def test_pais_absent_from_profile_not_prepopulated():
    """No country_pt in the profile → 'País' field doesn't enter the result."""
    result = pre_populate_answers(["País"], PROFILE_NO_LOCALE)
    assert "País" not in result


def test_english_level_absent_from_profile_not_prepopulated():
    """No english_level in the profile → 'English level' field doesn't enter the result."""
    result = pre_populate_answers(["English level"], PROFILE_NO_LOCALE)
    assert "English level" not in result


# The five per-label "absent from profile" tests that used to sit here were deleted
# rather than kept: their premise was profile-specific ("no demographics block → no
# answer via pre_populate_answers"), but once the EEO rules moved out of _RULES the
# assertion held for EVERY profile, configured or not — they could no longer go red.
# test_a_demographic_label_is_not_answered_by_the_general_ladder in test_demographics.py is the
# strictly stronger statement of what they meant, and demographic_answer's own
# unset-key tests cover the rest.


def test_office_available_true_returns_yes():
    """office_available=True → 'Yes'."""
    profile = {**PROFILE_NO_LOCALE, "office_available": True}
    result = pre_populate_answers(
        ["Are you able to work from the office at least two days per week?"], profile
    )
    assert result["Are you able to work from the office at least two days per week?"] == "Yes"


def test_office_available_false_returns_no():
    """office_available=False → 'No'."""
    profile = {**PROFILE_NO_LOCALE, "office_available": False}
    result = pre_populate_answers(
        ["Are you able to work from the office at least two days per week?"], profile
    )
    assert result["Are you able to work from the office at least two days per week?"] == "No"


def test_office_absent_from_profile_not_prepopulated():
    """No office_available in the profile → field doesn't enter the result."""
    result = pre_populate_answers(
        ["Are you able to work from the office at least two days per week?"], PROFILE_NO_LOCALE
    )
    assert "Are you able to work from the office at least two days per week?" not in result


def test_country_en_from_profile():
    """country_en in the profile → used as the answer for ^country$."""
    profile = {**PROFILE_NO_LOCALE, "country_en": "Germany"}
    result = pre_populate_answers(["Country"], profile)
    assert result["Country"] == "Germany"


def test_english_level_from_profile():
    """english_level in the profile → used in the proficiency rule."""
    profile = {**PROFILE_NO_LOCALE, "english_level": "Native"}
    result = pre_populate_answers(["English level"], profile)
    assert result["English level"] == "Native"
