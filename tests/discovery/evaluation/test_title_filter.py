"""Tests for the title blocklist that skips postings before any model call."""

from moonlighter.discovery.evaluation.title_filter import should_skip_by_title
from tests.discovery.evaluation.fake_evaluation import BLOCKLIST


def test_skip_exact_match():
    assert should_skip_by_title("Sales Manager", BLOCKLIST) == "sales"


def test_skip_case_insensitive():
    assert should_skip_by_title("MARKETING LEAD", BLOCKLIST) == "marketing"


def test_skip_substring_in_longer_title():
    assert should_skip_by_title("Senior Account Executive, EMEA", BLOCKLIST) == "account executive"


def test_skip_returns_none_for_tech_title():
    assert should_skip_by_title("Senior Software Engineer", BLOCKLIST) is None


def test_skip_returns_none_for_engineering_manager():
    assert should_skip_by_title("Engineering Manager, Platform", BLOCKLIST) is None


def test_skip_returns_none_empty_blocklist():
    assert should_skip_by_title("Sales Manager", []) is None


def test_skip_data_center_not_data_science():
    assert should_skip_by_title("Data Scientist, GTM", BLOCKLIST) is None
    assert should_skip_by_title("Data Center Electrical Engineer", BLOCKLIST) == "data center"


def test_skip_returns_first_matching_pattern():
    # title contains two patterns — returns the first one that matches
    result = should_skip_by_title("Sales Customer Success Specialist", BLOCKLIST)
    assert result in BLOCKLIST
