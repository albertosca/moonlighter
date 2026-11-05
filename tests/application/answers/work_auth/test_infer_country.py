"""infer_country: which job locations name a country confidently, and which never do."""

import pytest
from moonlighter.application.answers.work_auth import infer_country

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


def test_infer_country_other_canadian_markers_not_misread_as_us():
    assert infer_country("Montreal, Quebec", None) is None
    assert infer_country("Ottawa, Ontario, Canada", None) is None
    assert infer_country("Calgary, Alberta", None) is None


def test_infer_country_remote_with_no_location_signal_is_none():
    assert infer_country(None, None) is None
    assert infer_country("Remote", "remote") is None


# ── characterization pins: defaults, every marker, every phrasing, every alias ──


@pytest.mark.parametrize(
    "location",
    [
        "Sao Paulo",
        "Rio de Janeiro",
        "Porto Alegre",
        "Curitiba",
        "Recife",
        "Florianópolis",
        "Florianopolis",
        "Campinas",
    ],
)
def test_infer_country_brazil_from_each_city_marker(location):
    assert infer_country(location, None) == "brazil"


@pytest.mark.parametrize("location", ["U.S.", "U.S.A", "Seattle", "Austin", "Boston"])
def test_infer_country_us_from_each_marker(location):
    assert infer_country(location, None) == "united states"
