"""The key order of the JSON a scan CLI prints."""

from moonlighter.discovery.archive import ArchiveResult
from moonlighter.discovery.results import ScanKind, ScanReport, scan_report_to_dict
from moonlighter.discovery.sources.base import SourceStats

EXPECTED_KEYS = [
    "kind",
    "threshold",
    "spend_hit",
    "company",
    "found_but_known",
    "saved",
    "archive",
    "stats",
    "warning",
    "tip",
    "error",
]


def test_a_report_without_archive_or_stats_keeps_every_key_in_order():
    payload = scan_report_to_dict(ScanReport(kind=ScanKind.NO_NEW_JOBS))
    assert list(payload) == EXPECTED_KEYS
    assert payload["archive"] is None
    assert payload["stats"] is None


def test_a_report_with_archive_and_stats_keeps_the_same_key_order():
    report = ScanReport(
        kind=ScanKind.NO_NEW_JOBS,
        archive=ArchiveResult(),
        stats={"greenhouse": SourceStats(companies=1, jobs=2, errors=3)},
    )
    payload = scan_report_to_dict(report)
    assert list(payload) == EXPECTED_KEYS
    assert list(payload["stats"]["greenhouse"]) == ["companies", "jobs", "errors"]
