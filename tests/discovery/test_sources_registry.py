from gauntler.core.sources import Source
from gauntler.discovery.sources.http import (
    AshbyScanner,
    GreenhouseScanner,
    LeverScanner,
    RecruiteeScanner,
    WorkableScanner,
)
from gauntler.discovery.sources.registry import (
    LISTING_SOURCES,
    SOURCES,
    build_http_scanners,
)


def test_registry_covers_the_five_http_sources():
    assert set(SOURCES) == {
        Source.GREENHOUSE,
        Source.LEVER,
        Source.ASHBY,
        Source.WORKABLE,
        Source.RECRUITEE,
    }
    assert Source.LINKEDIN not in SOURCES  # browser-based, special-cased


def test_build_http_scanners_matches_the_old_hardcoded_dict():
    scanners = build_http_scanners()
    assert set(scanners) == {"greenhouse", "lever", "ashby", "workable", "recruitee"}
    assert isinstance(scanners["greenhouse"], GreenhouseScanner)
    assert isinstance(scanners["lever"], LeverScanner)
    assert isinstance(scanners["ashby"], AshbyScanner)
    assert isinstance(scanners["workable"], WorkableScanner)
    assert isinstance(scanners["recruitee"], RecruiteeScanner)


def test_listing_sources_is_derived_not_hardcoded():
    assert frozenset({"greenhouse", "lever", "ashby", "workable", "recruitee"}) == LISTING_SOURCES
    # membership works with a plain-string source (what staleness passes)
    assert "greenhouse" in LISTING_SOURCES
    assert "workable" in LISTING_SOURCES
    assert "recruitee" in LISTING_SOURCES
    assert "linkedin" not in LISTING_SOURCES


def test_all_five_http_specs_support_listing():
    assert all(spec.supports_listing for spec in SOURCES.values())
