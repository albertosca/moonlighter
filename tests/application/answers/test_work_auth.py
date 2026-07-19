from moonlighter.application.answers.work_auth import infer_country, resolve_work_auth

WA_CONFIG = {
    "work_authorization": {
        "citizenship_country": "brazil",
        "authorized_answer": "Yes",
        "not_authorized_answer": "No",
    }
}


# ── infer_country (conservador) ───────────────────────────────────────────────


def test_infer_country_brazil_from_location():
    assert infer_country("São Paulo, Brazil", None) == "brazil"
    assert infer_country("Belo Horizonte, MG, Brasil", None) == "brazil"


def test_infer_country_us_from_location():
    assert infer_country("San Francisco, CA, United States", None) == "united states"
    assert infer_country("New York, NY, USA", None) == "united states"


def test_infer_country_unknown_returns_none():
    # remote with no explicit country → cannot be presumed
    assert infer_country("Remote", "remote") is None
    assert infer_country(None, "remote") is None
    assert infer_country("", None) is None


# ── resolve_work_auth ─────────────────────────────────────────────────────────


def test_resolve_authorized_for_brazil():
    r = resolve_work_auth("Are you authorized to work in this location?", "brazil", WA_CONFIG)
    assert r == "Yes"


def test_resolve_sponsorship_for_brazil():
    r = resolve_work_auth("Will you require visa sponsorship?", "brazil", WA_CONFIG)
    assert r == "No"


def test_resolve_authorized_for_us_is_no():
    r = resolve_work_auth(
        "Are you legally authorized to work in the US?", "united states", WA_CONFIG
    )
    assert r == "No"


def test_resolve_sponsorship_for_us_is_yes():
    r = resolve_work_auth(
        "Do you require sponsorship now or in the future?", "united states", WA_CONFIG
    )
    assert r == "Yes"


def test_resolve_unknown_country_needs_review():
    r = resolve_work_auth("Are you authorized to work here?", None, WA_CONFIG)
    assert r == "__NEEDS_REVIEW__"


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
    r = resolve_work_auth(
        "Are you authorized to work in this location?", "brazil", WA_CONFIG_EMPTY_CITIZENSHIP
    )
    assert r == "__NEEDS_REVIEW__"


def test_missing_citizenship_needs_review():
    """citizenship_country missing from config → same behavior as empty."""
    r = resolve_work_auth(
        "Are you authorized to work in this location?", "brazil", WA_CONFIG_NO_CITIZENSHIP
    )
    assert r == "__NEEDS_REVIEW__"


# ── C2: edge cases (regressions) ────────────────────────────────────────────


def test_infer_country_canada_not_misread_as_us():
    """', ca' must NOT match 'Canada' (from 'ca-nada') — otherwise a Canadian job becomes US."""
    assert infer_country("Toronto, Canada", None) is None
    assert infer_country("Vancouver, BC, Canada", None) is None


def test_infer_country_us_state_codes_still_match():
    # cities OUTSIDE the marker list → forces the state regex code path
    # 'CA' is handled separately (ambiguous, see the E8 T2 section below) — not tested here.
    assert infer_country("Tacoma, WA", None) == "united states"
    assert infer_country("Dallas, TX", None) == "united states"


def test_resolve_citizenship_locale_normalized():
    """A non-canonical citizenship_country ('Brasil'/'Brazil'/'BR') must match 'brazil'."""
    for form in ("Brasil", "Brazil", "BR", " brazil "):
        cfg = {"work_authorization": {"citizenship_country": form}}
        r = resolve_work_auth("Are you authorized to work here?", "brazil", cfg)
        assert r == "Yes", f"failed for {form!r}"


def test_resolve_us_citizenship_normalized():
    """citizenship_country in US form ('USA') normalizes and matches country 'united states'."""
    cfg = {"work_authorization": {"citizenship_country": "USA"}}
    r = resolve_work_auth("Are you authorized to work here?", "united states", cfg)
    assert r == "Yes"


def test_resolve_unrecognized_citizenship_needs_review():
    """Unrecognized citizenship country (neither BR nor US) → review (conservative)."""
    cfg = {"work_authorization": {"citizenship_country": "Portugal"}}
    r = resolve_work_auth("Are you authorized to work here?", "united states", cfg)
    assert r == "__NEEDS_REVIEW__"


# ── E8 T2: ", CA" is always ambiguous — conservative rule, never a guess ─────
#
# "CA" is ambiguous: US-state code (California) OR country code (Canada, ISO
# 3166 alpha-2). Rather than disambiguate by enumerating Canadian cities (the
# allowlist approach tried and reverted here), the chosen rule is: ANY ", CA"
# location resolves to None (-> __NEEDS_REVIEW__ downstream), regardless of
# whether the city is Canadian or genuinely Californian. This means legitimate
# California postings also land in manual review — an accepted tradeoff over
# ever guessing wrong about work authorization.


def test_infer_country_canadian_city_with_ambiguous_ca_country_code_is_not_us():
    """'Toronto, CA' and 'Vancouver, CA' use CA as the country code (Canada),
    not the US state code — must never resolve to 'united states'."""
    assert infer_country("Toronto, CA", None) is None
    assert infer_country("Vancouver, CA", None) is None


def test_infer_country_ca_is_always_ambiguous_never_resolves_to_a_country():
    """Conservative rule holds for ANY ', CA' location: a made-up US-California
    city and a made-up Canadian city both resolve to None (needs review) —
    the rule does not special-case real Canadian markers or real CA cities."""
    assert infer_country("Anytown, CA", None) is None
    assert infer_country("Notrealburg, CA", None) is None
    # Real US cities with ', CA' are no longer resolved either: conservative
    # by design, this catches genuine California postings too.
    assert infer_country("Los Angeles, CA", None) is None
    assert infer_country("Sacramento, CA", None) is None


def test_infer_country_us_state_ny_still_resolves_to_us():
    """Control: a non-ambiguous US state code (NY) is unaffected by the CA
    conservative rule and still resolves to 'united states'."""
    assert infer_country("Buffalo, NY", None) == "united states"


def test_resolve_work_auth_for_ambiguous_canada_string_needs_review_not_us():
    """End to end: an authorization field with location 'Toronto, CA' (the
    inferred country must be None, not 'united states') cannot answer as if
    the job were in the US — it must fall through to review."""
    country = infer_country("Toronto, CA", None)
    assert country is None
    r = resolve_work_auth("Are you authorized to work in the US?", country, WA_CONFIG)
    assert r == "__NEEDS_REVIEW__"


def test_infer_country_other_canadian_markers_not_misread_as_us():
    assert infer_country("Montreal, Quebec", None) is None
    assert infer_country("Ottawa, Ontario, Canada", None) is None
    assert infer_country("Calgary, Alberta", None) is None


def test_infer_country_remote_with_no_location_signal_is_none():
    assert infer_country(None, None) is None
    assert infer_country("Remote", "remote") is None
