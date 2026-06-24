from candidatador.application.answers.work_auth import infer_country, resolve_work_auth

WA_CONFIG = {
    "work_authorization": {
        "citizenship_country": "brazil",
        "authorized_answer": "Yes",
        "not_authorized_answer": "No",
        "needs_review_sentinel": "__NEEDS_REVIEW__",
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
    # remoto sem país explícito → não dá para presumir
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
        "needs_review_sentinel": "__NEEDS_REVIEW__",
    }
}

WA_CONFIG_NO_CITIZENSHIP = {
    "work_authorization": {
        "authorized_answer": "Yes",
        "not_authorized_answer": "No",
        "needs_review_sentinel": "__NEEDS_REVIEW__",
    }
}


def test_empty_citizenship_needs_review_even_with_known_country():
    """citizenship_country vazio → nunca chuta o país, sempre __NEEDS_REVIEW__."""
    r = resolve_work_auth(
        "Are you authorized to work in this location?", "brazil", WA_CONFIG_EMPTY_CITIZENSHIP
    )
    assert r == "__NEEDS_REVIEW__"


def test_missing_citizenship_needs_review():
    """citizenship_country ausente do config → mesmo comportamento que vazio."""
    r = resolve_work_auth(
        "Are you authorized to work in this location?", "brazil", WA_CONFIG_NO_CITIZENSHIP
    )
    assert r == "__NEEDS_REVIEW__"
