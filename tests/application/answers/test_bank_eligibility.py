"""The bank's pure gatekeeping: question normalisation, eligible kinds and sensitive labels."""

import pytest
from moonlighter.application.answers.answer_bank import is_sensitive_label


@pytest.mark.parametrize("label", ["Preferências de horário", "What is your age?", "Age (years)"])
def test_is_sensitive_label_pins_the_deliberate_over_match_and_the_age_word(label):
    assert is_sensitive_label(label) is True
