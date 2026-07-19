from dataclasses import dataclass

from gauntler.core.sources import Source
from gauntler.discovery.sources import http
from gauntler.discovery.sources.base import BaseScanner


@dataclass(frozen=True)
class ScannerSpec:
    scanner_class: type[BaseScanner]
    supports_listing: bool


# The single source of truth for HTTP-scanned ATS platforms. LinkedIn is NOT here:
# it is browser-based (LinkedInScanner(page)) and dispatched separately.
SOURCES: dict[Source, ScannerSpec] = {
    Source.GREENHOUSE: ScannerSpec(http.GreenhouseScanner, supports_listing=True),
    Source.LEVER: ScannerSpec(http.LeverScanner, supports_listing=True),
    Source.ASHBY: ScannerSpec(http.AshbyScanner, supports_listing=True),
    Source.WORKABLE: ScannerSpec(http.WorkableScanner, supports_listing=True),
    Source.RECRUITEE: ScannerSpec(http.RecruiteeScanner, supports_listing=True),
}


def build_http_scanners() -> dict[str, BaseScanner]:
    """A fresh {source: scanner_instance} dict for the HTTP sources, built from SOURCES.

    Resolves each scanner class via a live attribute lookup on gauntler.discovery.sources.http
    (rather than the class reference captured in SOURCES at import time) so that
    unittest.mock.patch("gauntler.discovery.sources.http.GreenhouseScanner") still works —
    the same as it did with the old hardcoded dict.
    """
    return {
        source.value: getattr(http, spec.scanner_class.__name__)()
        for source, spec in SOURCES.items()
    }


# Sources whose staleness can be checked by re-listing (derived from the registry,
# not hand-maintained). frozenset[str] so a plain-string source matches in `in` tests.
LISTING_SOURCES: frozenset[str] = frozenset(
    source.value for source, spec in SOURCES.items() if spec.supports_listing
)
