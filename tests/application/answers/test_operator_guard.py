"""Pins which answers the operator guard flags, and which marker it names."""

import pytest
from moonlighter.application.answers.operator_guard import find_operator_marker

from tests.application.operator_incidents import OPERATOR_NOTE_ADDRESS, OPERATOR_NOTE_REFERENCES


@pytest.mark.parametrize(
    ("answer", "marker"),
    [
        (OPERATOR_NOTE_REFERENCES, "the candidate"),
        (OPERATOR_NOTE_ADDRESS, "please supply"),
    ],
)
def test_both_live_incidents_are_flagged(answer, marker):
    assert find_operator_marker(answer) == marker


def test_a_first_person_answer_is_not_flagged():
    assert find_operator_marker("I have shipped Elixir in production since 2016.") is None


def test_matching_ignores_case():
    assert find_operator_marker("PLEASE UPLOAD the file") == "please upload"


def test_the_marker_named_is_the_first_in_the_list_not_the_first_in_the_text():
    assert find_operator_marker("Please provide details about the applicant.") == "the applicant"
