"""The messages ScanReport raises, and which one wins when several checks fail."""

import pytest

from moonlighter.discovery.scan.results import ScanKind, ScanReport


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


def test_scan_report_all_known_requires_a_company_and_a_count(three_jobs):
    with pytest.raises(ValueError, match="all_known"):
        ScanReport(kind=ScanKind.ALL_KNOWN, found_but_known=3)
    with pytest.raises(ValueError, match="all_known"):
        ScanReport(kind=ScanKind.ALL_KNOWN, company="acme")


def test_scan_report_no_open_jobs_requires_a_company():
    with pytest.raises(ValueError, match="no_open_jobs"):
        ScanReport(kind=ScanKind.NO_OPEN_JOBS)


def test_scan_report_error_is_the_unknown_source_message_and_nothing_else(three_jobs):
    with pytest.raises(ValueError, match="unknown_source"):
        ScanReport(kind=ScanKind.UNKNOWN_SOURCE)
    with pytest.raises(ValueError, match="unknown_source"):
        ScanReport(kind=ScanKind.EVALUATED, saved=three_jobs, error="boom")


def test_scan_report_only_an_evaluated_scan_carries_results(three_jobs):
    # The old dataclass used `company` and `no_new_jobs` as renderer mode
    # switches that silently discarded saved/spend_hit. The kind is explicit
    # now, and carrying results under any other kind is a producer bug.
    with pytest.raises(ValueError, match="evaluated"):
        ScanReport(kind=ScanKind.NO_NEW_JOBS, saved=three_jobs)
    with pytest.raises(ValueError, match="evaluated"):
        ScanReport(kind=ScanKind.NO_OPEN_JOBS, company="acme", spend_hit=True)
