"""Tests for the engagement section built from the profile preferences."""

from moonlighter.discovery.evaluation.engagement import engagement_section


def test_the_engagement_section_is_stripped_and_ends_with_a_blank_line():
    section = engagement_section({"preferences": {"engagement": "  permanent  "}})
    assert "targets permanent positions" in section
    assert section.endswith("\n\n")
