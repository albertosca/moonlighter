from datetime import datetime

from moonlighter.discovery.sources.base import (
    RawJob,
    ScannerSessionExpiredError,
    join_locations,
    normalize_remote_type,
    remote_type_from_workplace,
    remote_types_mentioned,
)


def test_rawjob_defaults():
    job = RawJob(source="greenhouse", company="Stripe", title="Eng", url="https://x.com")
    assert job.remote_type is None
    assert job.salary_source is None


def test_normalize_remote_type():
    assert normalize_remote_type("Remote - US") == "remote"
    assert normalize_remote_type("Hybrid, São Paulo") == "hybrid"
    assert normalize_remote_type(None) is None


def test_normalize_remote_type_speaks_portuguese():
    # Live bug (iFood #2811, seen 2026-08-24): location said "Remoto" and the
    # derived remote_type said 'onsite' — the vocabulary was English-only.
    assert normalize_remote_type("Remoto") == "remote"
    assert normalize_remote_type("Híbrido - São Paulo") == "hybrid"
    assert normalize_remote_type("Hibrido") == "hybrid"
    assert normalize_remote_type("Presencial - São Paulo") == "onsite"


def test_a_bare_place_name_is_unknown_not_onsite():
    # The old default invented 'onsite' for any unrecognized location. Once
    # the regional eligibility filter started cutting onsite/hybrid outside
    # Belo Horizonte deterministically (2026-08-24), an invented 'onsite'
    # became an invented archive — remote_type must be explicit or None.
    assert normalize_remote_type("New York, NY") is None
    assert normalize_remote_type("São Paulo") is None


def test_onsite_only_when_explicit():
    assert normalize_remote_type("On-site, Austin") == "onsite"
    assert normalize_remote_type("Onsite - Berlin") == "onsite"
    assert normalize_remote_type("In office, NYC") == "onsite"


def test_normalize_remote_case_insensitive():
    assert normalize_remote_type("REMOTE") == "remote"
    assert normalize_remote_type("Remote") == "remote"


def test_normalize_hybrid_variations():
    assert normalize_remote_type("Hybrid, São Paulo") == "hybrid"
    assert normalize_remote_type("Hybrid-Remote") == "hybrid"


def test_normalize_onsite_in_office():
    assert normalize_remote_type("In-Office") == "onsite"


def test_normalize_onsite_on_site():
    assert normalize_remote_type("On-Site, NY") == "onsite"


def test_normalize_empty_string_returns_none():
    assert normalize_remote_type("") is None


def test_normalize_unknown_string_is_none():
    assert normalize_remote_type("negotiable") is None


def test_normalize_us_only_string():
    assert normalize_remote_type("United States") is None


def test_rawjob_with_all_fields():
    now = datetime.now()
    job = RawJob(
        source="greenhouse",
        company="Stripe",
        title="Eng",
        url="https://x.com",
        location="Remote",
        remote_type="remote",
        description="desc",
        posted_at=now,
        salary_min=100000,
        salary_max=150000,
        salary_currency="USD",
        salary_source="stated",
    )
    assert job.salary_min == 100000
    assert job.salary_currency == "USD"
    assert job.posted_at == now


def test_rawjob_source_values():
    for source in ("greenhouse", "lever", "ashby", "linkedin"):
        job = RawJob(source=source, company="Co", title="Eng", url="https://x.com")
        assert job.source == source


def test_rawjob_posted_at_is_datetime():
    now = datetime.now()
    job = RawJob(source="greenhouse", company="Co", title="Eng", url="https://x.com", posted_at=now)
    assert isinstance(job.posted_at, datetime)


def test_scanner_session_expired_error_is_an_exception():
    error = ScannerSessionExpiredError("session expired")
    assert isinstance(error, Exception)
    assert str(error) == "session expired"


def test_remote_type_from_workplace_maps_api_vocabularies():
    assert remote_type_from_workplace("onsite") == "onsite"
    assert remote_type_from_workplace("OnSite") == "onsite"
    assert remote_type_from_workplace("Hybrid") == "hybrid"
    assert remote_type_from_workplace("remote") == "remote"
    assert remote_type_from_workplace("unspecified") is None
    assert remote_type_from_workplace("") is None
    assert remote_type_from_workplace(None) is None
    assert remote_type_from_workplace(42) is None  # malformed payload, never a crash


def test_remote_types_mentioned_reports_every_kind_in_a_segment():
    assert remote_types_mentioned("ONSITE or REMOTE") == {"onsite", "remote"}
    assert remote_types_mentioned("Remote (US)") == {"remote"}
    assert remote_types_mentioned("In-Office") == {"onsite"}
    assert remote_types_mentioned("Memphis, TN") == set()
    assert remote_types_mentioned("") == set()


def test_join_locations_puts_primary_first_and_drops_repeats():
    assert join_locations("Seattle", ["Dallas", "Seattle", "Dallas", "Remote (US)"]) == (
        "Seattle; Dallas; Remote (US)"
    )


def test_join_locations_ignores_blank_and_non_string_entries():
    assert join_locations(None, [" ", None, "Berlin", 3]) == "Berlin"
    assert join_locations("  ", []) is None
    assert join_locations(None, None) is None


def test_join_locations_keeps_only_the_first_eight():
    places = [f"City {number}" for number in range(12)]
    joined = join_locations(places[0], places[1:])
    assert joined == "; ".join(places[:8])
