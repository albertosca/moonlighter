"""The registry of HTTP-scanned ATS platforms, and the source sets derived from it."""

import importlib
from dataclasses import dataclass

from moonlighter.core.sources import Source
from moonlighter.discovery.sources.base import BaseScanner
from moonlighter.discovery.sources.company_boards.ashby import AshbyScanner
from moonlighter.discovery.sources.company_boards.greenhouse import GreenhouseScanner
from moonlighter.discovery.sources.company_boards.inhire import InHireScanner
from moonlighter.discovery.sources.company_boards.lever import LeverScanner
from moonlighter.discovery.sources.company_boards.recruitee import RecruiteeScanner
from moonlighter.discovery.sources.company_boards.smartrecruiters import SmartRecruitersScanner
from moonlighter.discovery.sources.company_boards.workable import WorkableScanner


@dataclass(frozen=True)
class ScannerSpec:
    scanner_class: type[BaseScanner]
    supports_listing: bool


# The single source of truth for HTTP-scanned ATS platforms. LinkedIn is NOT here:
# it is browser-based (LinkedInScanner(page)) and dispatched separately.
SOURCES: dict[Source, ScannerSpec] = {
    Source.GREENHOUSE: ScannerSpec(GreenhouseScanner, supports_listing=True),
    Source.LEVER: ScannerSpec(LeverScanner, supports_listing=True),
    Source.ASHBY: ScannerSpec(AshbyScanner, supports_listing=True),
    Source.WORKABLE: ScannerSpec(WorkableScanner, supports_listing=True),
    Source.RECRUITEE: ScannerSpec(RecruiteeScanner, supports_listing=True),
    Source.INHIRE: ScannerSpec(InHireScanner, supports_listing=True),
    Source.SMARTRECRUITERS: ScannerSpec(SmartRecruitersScanner, supports_listing=True),
}


def build_http_scanners() -> dict[str, BaseScanner]:
    """A fresh {source: scanner_instance} dict for the HTTP sources, built from SOURCES.

    Resolves each scanner class via a live attribute lookup on the class's own module
    (rather than the class reference captured in SOURCES at import time) so that
    unittest.mock.patch("moonlighter.discovery.sources.company_boards.greenhouse.GreenhouseScanner")
    still works — the same as it did with the old hardcoded dict.
    """
    return {
        source.value: getattr(
            importlib.import_module(spec.scanner_class.__module__), spec.scanner_class.__name__
        )()
        for source, spec in SOURCES.items()
    }


# Sources whose staleness can be checked by re-listing (derived from the registry,
# not hand-maintained). frozenset[str] so a plain-string source matches in `in` tests.
LISTING_SOURCES: frozenset[str] = frozenset(
    source.value for source, spec in SOURCES.items() if spec.supports_listing
)

# Portal-wide feeds: config-gated, keyword-filtered, and not per-company —
# staleness cannot be checked by re-listing a company, so staleness.py reports
# them as one aggregate line per source instead of one line per job's company.
PORTAL_SOURCES: frozenset[str] = frozenset(
    {"gupy", "remoteok", "remotive", "weworkremotely", "hn_whoishiring"}
)
