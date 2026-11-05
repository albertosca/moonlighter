"""The JSON a scan CLI prints: its key order, its facts, and that it serialises."""

import json

from moonlighter.discovery.archive import ArchiveResult
from moonlighter.discovery.scan.results import ScanKind, ScanResult, scan_report_to_dict
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
    payload = scan_report_to_dict(ScanResult(kind=ScanKind.NO_NEW_JOBS))
    assert list(payload) == EXPECTED_KEYS
    assert payload["archive"] is None
    assert payload["stats"] is None


def test_a_report_with_archive_and_stats_keeps_the_same_key_order():
    report = ScanResult(
        kind=ScanKind.NO_NEW_JOBS,
        archive=ArchiveResult(),
        stats={"greenhouse": SourceStats(companies=1, jobs=2, errors=3)},
    )
    payload = scan_report_to_dict(report)
    assert list(payload) == EXPECTED_KEYS
    assert list(payload["stats"]["greenhouse"]) == ["companies", "jobs", "errors"]


def test_scan_report_to_dict_is_json_serialisable_and_carries_the_facts(three_jobs):

    report = ScanResult(
        kind=ScanKind.EVALUATED,
        saved=three_jobs,
        spend_hit=True,
        threshold=7.0,
        archive=ArchiveResult(archived=[{"id": "1", "company": "Acme"}], max_age_days=30),
        warning="⚠️  greenhouse: 0 jobs",
        stats={"greenhouse": SourceStats(companies=3, jobs=2, errors=1)},
        company="acme",
    )
    payload = scan_report_to_dict(report)
    json.dumps(payload)  # raises on anything non-serialisable
    assert payload["kind"] == "evaluated"
    assert payload["spend_hit"] is True
    assert payload["threshold"] == 7.0
    assert payload["company"] == "acme"
    assert [entry["title"] for entry in payload["saved"]] == [job.title for job in three_jobs]
    assert payload["saved"][0]["score"] == 9.0
    assert payload["archive"] == {
        "archived": [{"id": "1", "company": "Acme"}],
        "aged": [],
        "max_age_days": 30,
        "failed_companies": [],
        "to_confirm": [],
    }
    assert payload["stats"] == {"greenhouse": {"companies": 3, "jobs": 2, "errors": 1}}
    assert payload["warning"] == "⚠️  greenhouse: 0 jobs"
    assert payload["error"] is None


def test_scan_report_to_dict_pins_the_found_but_known_key_on_all_known(three_jobs):
    # A CLI consumer reads found_but_known by that exact key over the wire --
    # renaming the dict literal (not the dataclass field) left every other
    # test in the suite green before this test existed (mutation checked,
    # reverted).

    report = ScanResult(kind=ScanKind.ALL_KNOWN, threshold=7.0, company="acme", found_but_known=3)
    payload = scan_report_to_dict(report)
    assert "found_but_known" in payload
    assert payload["found_but_known"] == 3
