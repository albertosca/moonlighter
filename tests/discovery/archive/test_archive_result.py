"""The field order of ArchiveResult, which the CLI prints as JSON."""

from dataclasses import asdict

from moonlighter.discovery.archive import ArchiveResult


def test_archive_result_serialises_its_fields_in_a_fixed_order():
    assert list(asdict(ArchiveResult())) == [
        "archived",
        "aged",
        "max_age_days",
        "failed_companies",
        "to_confirm",
    ]
