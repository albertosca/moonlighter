"""The messages ScanReport raises, and which one wins when several checks fail."""

import pytest
from moonlighter.discovery.results import ScanKind, ScanReport


def test_the_error_message_names_the_unknown_source_rule():
    with pytest.raises(ValueError, match="unknown_source") as raised:
        ScanReport(kind=ScanKind.UNKNOWN_SOURCE)
    assert str(raised.value) == "ScanReport.error is set exactly when kind is unknown_source"


def test_the_company_message_names_the_kind():
    with pytest.raises(ValueError, match="no_open_jobs") as raised:
        ScanReport(kind=ScanKind.NO_OPEN_JOBS)
    assert str(raised.value) == "ScanReport kind no_open_jobs names a company; company is required"


def test_the_found_but_known_message_names_the_all_known_rule():
    with pytest.raises(ValueError, match="all_known") as raised:
        ScanReport(kind=ScanKind.NO_NEW_JOBS, found_but_known=2)
    assert str(raised.value) == (
        "ScanReport.found_but_known is positive exactly when kind is all_known"
    )


def test_the_results_message_says_only_an_evaluated_report_carries_them():
    with pytest.raises(ValueError, match="evaluated") as raised:
        ScanReport(kind=ScanKind.NO_NEW_JOBS, spend_hit=True)
    assert str(raised.value) == "only an evaluated ScanReport carries saved/spend_hit"


def test_the_error_check_runs_before_the_company_check():
    with pytest.raises(ValueError, match=r"ScanReport\.error") as raised:
        ScanReport(kind=ScanKind.NO_OPEN_JOBS, error="boom")
    assert "company is required" not in str(raised.value)


def test_the_company_check_runs_before_the_found_but_known_check():
    with pytest.raises(ValueError, match="company is required"):
        ScanReport(kind=ScanKind.ALL_KNOWN)


def test_the_found_but_known_check_runs_before_the_results_check():
    with pytest.raises(ValueError, match="found_but_known"):
        ScanReport(kind=ScanKind.NO_NEW_JOBS, found_but_known=1, spend_hit=True)
