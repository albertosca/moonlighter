from gauntler.application.answers.work_auth import infer_country, resolve_work_auth

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
    }
}

WA_CONFIG_NO_CITIZENSHIP = {
    "work_authorization": {
        "authorized_answer": "Yes",
        "not_authorized_answer": "No",
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


# ── C2: edge cases (regressões) ───────────────────────────────────────────────


def test_infer_country_canada_not_misread_as_us():
    """', ca' NÃO pode casar 'Canada' (de 'ca-nada') — senão vaga canadense vira US."""
    assert infer_country("Toronto, Canada", None) is None
    assert infer_country("Vancouver, BC, Canada", None) is None


def test_infer_country_us_state_codes_still_match():
    # cidades FORA da lista de markers → força o caminho do regex de estado
    assert infer_country("Sacramento, CA", None) == "united states"
    assert infer_country("Tacoma, WA", None) == "united states"
    assert infer_country("Dallas, TX", None) == "united states"


def test_resolve_citizenship_locale_normalized():
    """citizenship_country não-canônico ('Brasil'/'Brazil'/'BR') deve casar 'brazil'."""
    for form in ("Brasil", "Brazil", "BR", " brazil "):
        cfg = {"work_authorization": {"citizenship_country": form}}
        r = resolve_work_auth("Are you authorized to work here?", "brazil", cfg)
        assert r == "Yes", f"falhou para {form!r}"


def test_resolve_us_citizenship_normalized():
    """citizenship_country em forma US ('USA') normaliza e casa país 'united states'."""
    cfg = {"work_authorization": {"citizenship_country": "USA"}}
    r = resolve_work_auth("Are you authorized to work here?", "united states", cfg)
    assert r == "Yes"


def test_resolve_unrecognized_citizenship_needs_review():
    """País de cidadania não-reconhecido (nem BR nem US) → review (conservador)."""
    cfg = {"work_authorization": {"citizenship_country": "Portugal"}}
    r = resolve_work_auth("Are you authorized to work here?", "united states", cfg)
    assert r == "__NEEDS_REVIEW__"


# ── E8 T2: Canada false-positive (real bug found and fixed here) ─────────────
#
# 'CA' é ambíguo: sigla de estado americano (California) OU sigla de país
# (Canada, ISO 3166 alpha-2). Antes do fix, uma vaga formatada como
# "Toronto, CA" (país abreviado) batia em _US_STATE_RE (', ca' = California) e
# era classificada como 'united states' — um falso positivo REAL, distinto do
# caso hipotético 'Ca-nada' já coberto acima. Isso faria resolve_work_auth
# responder autorização/sponsorship como se a vaga fosse nos EUA, quando na
# verdade é uma vaga canadense sem país suportado -> deveria ser
# __NEEDS_REVIEW__, nunca 'a vaga é US'.


def test_infer_country_canadian_city_with_ambiguous_ca_country_code_is_not_us():
    """'Toronto, CA' e 'Vancouver, CA' usam CA como sigla de país (Canada), não
    de estado americano. Antes do fix isso retornava 'united states' — bug real."""
    assert infer_country("Toronto, CA", None) is None
    assert infer_country("Vancouver, CA", None) is None


def test_infer_country_us_california_city_with_ca_still_resolves_to_us():
    """Controle: cidades americanas reais com ', CA' (Sacramento, Los Angeles)
    continuam corretamente inferidas como US mesmo após o fix — o fix só
    desliga o match quando há um marcador canadense explícito na string."""
    assert infer_country("Los Angeles, CA", None) == "united states"
    assert infer_country("Sacramento, CA", None) == "united states"


def test_resolve_work_auth_for_ambiguous_canada_string_needs_review_not_us():
    """Fim a fim: campo de autorização com localização 'Toronto, CA' (o país
    inferido deve ser None, não 'united states') não pode responder como se
    fosse autorização/sponsorship nos EUA — precisa cair em review."""
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
