from gauntler.core.sources import Source
from gauntler.discovery.sources.http import AshbyScanner, GreenhouseScanner, LeverScanner
from gauntler.discovery.sources.registry import (
    LISTING_SOURCES,
    SOURCES,
    build_http_scanners,
)


def test_registry_covers_the_three_http_sources():
    assert set(SOURCES) == {Source.GREENHOUSE, Source.LEVER, Source.ASHBY}
    assert Source.LINKEDIN not in SOURCES  # browser-based, special-cased


def test_build_http_scanners_matches_the_old_hardcoded_dict():
    scanners = build_http_scanners()
    assert set(scanners) == {"greenhouse", "lever", "ashby"}
    assert isinstance(scanners["greenhouse"], GreenhouseScanner)
    assert isinstance(scanners["lever"], LeverScanner)
    assert isinstance(scanners["ashby"], AshbyScanner)


def test_listing_sources_is_derived_not_hardcoded():
    assert frozenset({"greenhouse", "lever", "ashby"}) == LISTING_SOURCES
    # membership works with a plain-string source (what staleness passes)
    assert "greenhouse" in LISTING_SOURCES
    assert "linkedin" not in LISTING_SOURCES


def test_all_three_http_specs_support_listing():
    assert all(spec.supports_listing for spec in SOURCES.values())
