"""resolve_work_auth: the answer per field kind, country and configured citizenship."""

import pytest

from moonlighter.application.answers.rules.work_auth import infer_country, resolve_work_auth

WA_CONFIG = {
    "work_authorization": {
        "citizenship_country": "brazil",
        "authorized_answer": "Yes",
        "not_authorized_answer": "No",
    }
}


# ── resolve_work_auth ─────────────────────────────────────────────────────────


def test_resolve_authorized_for_brazil():
    answer = resolve_work_auth("Are you authorized to work in this location?", "brazil", WA_CONFIG)
    assert answer == "Yes"


def test_resolve_sponsorship_for_brazil():
    answer = resolve_work_auth("Will you require visa sponsorship?", "brazil", WA_CONFIG)
    assert answer == "No"


def test_resolve_authorized_for_us_is_no():
    answer = resolve_work_auth(
        "Are you legally authorized to work in the US?", "united states", WA_CONFIG
    )
    assert answer == "No"


def test_resolve_sponsorship_for_us_is_yes():
    answer = resolve_work_auth(
        "Do you require sponsorship now or in the future?", "united states", WA_CONFIG
    )
    assert answer == "Yes"


def test_resolve_unknown_country_needs_review():
    answer = resolve_work_auth("Are you authorized to work here?", None, WA_CONFIG)
    assert answer == "__NEEDS_REVIEW__"


def test_resolve_non_work_auth_field_returns_none():
    assert resolve_work_auth("What is your favorite language?", "brazil", WA_CONFIG) is None


WA_CONFIG_EMPTY_CITIZENSHIP = {
    "work_authorization": {
        "citizenship_country": "",
        "authorized_answer": "Yes",
        "not_authorized_answer": "No",
    }
}


WA_CONFIG_NO_CITIZENSHIP = {
    "work_authorization": {
        "authorized_answer": "Yes",
        "not_authorized_answer": "No",
    }
}


def test_empty_citizenship_needs_review_even_with_known_country():
    """citizenship_country empty → never guesses the country, always __NEEDS_REVIEW__."""
    answer = resolve_work_auth(
        "Are you authorized to work in this location?", "brazil", WA_CONFIG_EMPTY_CITIZENSHIP
    )
    assert answer == "__NEEDS_REVIEW__"


def test_missing_citizenship_needs_review():
    """citizenship_country missing from config → same behavior as empty."""
    answer = resolve_work_auth(
        "Are you authorized to work in this location?", "brazil", WA_CONFIG_NO_CITIZENSHIP
    )
    assert answer == "__NEEDS_REVIEW__"


# ── C2: edge cases (regressions) ────────────────────────────────────────────


def test_resolve_citizenship_locale_normalized():
    """A non-canonical citizenship_country ('Brasil'/'Brazil'/'BR') must match 'brazil'."""
    for form in ("Brasil", "Brazil", "BR", " brazil "):
        config = {"work_authorization": {"citizenship_country": form}}
        answer = resolve_work_auth("Are you authorized to work here?", "brazil", config)
        assert answer == "Yes", f"failed for {form!r}"


def test_resolve_us_citizenship_normalized():
    """citizenship_country in US form ('USA') normalizes and matches country 'united states'."""
    config = {"work_authorization": {"citizenship_country": "USA"}}
    answer = resolve_work_auth("Are you authorized to work here?", "united states", config)
    assert answer == "Yes"


def test_resolve_unrecognized_citizenship_needs_review():
    """Unrecognized citizenship country (neither BR nor US) → review (conservative)."""
    config = {"work_authorization": {"citizenship_country": "Portugal"}}
    answer = resolve_work_auth("Are you authorized to work here?", "united states", config)
    assert answer == "__NEEDS_REVIEW__"


# ── E8 T2: ", CA" is always ambiguous — conservative rule, never a guess ─────
#
# The rule and its rationale are written out in test_infer_country.py.


def test_resolve_work_auth_for_ambiguous_canada_string_needs_review_not_us():
    """End to end: an authorization field with location 'Toronto, CA' (the
    inferred country must be None, not 'united states') cannot answer as if
    the job were in the US — it must fall through to review.
    """
    country = infer_country("Toronto, CA", None)
    assert country is None
    answer = resolve_work_auth("Are you authorized to work in the US?", country, WA_CONFIG)
    assert answer == "__NEEDS_REVIEW__"


# ── characterization pins: defaults, every marker, every phrasing, every alias ──


def test_resolve_defaults_the_not_authorized_answer_to_no():
    config = {"work_authorization": {"citizenship_country": "brazil"}}
    assert resolve_work_auth("Are you authorized to work here?", "united states", config) == "No"


@pytest.mark.parametrize(
    "label",
    [
        "Do you have work authorization?",
        "Can you legally work in this country?",
        "Do you hold a work permit?",
        "Are you eligible to work here?",
    ],
)
def test_resolve_recognises_each_authorization_phrasing(label):
    assert resolve_work_auth(label, "brazil", WA_CONFIG) == "Yes"


@pytest.mark.parametrize("label", ["Do you require a visa?", "Will you need visa-related support?"])
def test_resolve_recognises_each_sponsorship_phrasing(label):
    assert resolve_work_auth(label, "brazil", WA_CONFIG) == "No"


@pytest.mark.parametrize(
    "citizenship", ["united states", "US", "u.s.", "U.S.A", "United States of America"]
)
def test_resolve_accepts_each_us_citizenship_alias(citizenship):
    config = {"work_authorization": {"citizenship_country": citizenship}}
    assert resolve_work_auth("Are you authorized to work here?", "united states", config) == "Yes"
