from moonlighter.application.answers.option_matcher import (
    match_option_locally,
)

CEFR = [
    "I can read simple texts",
    "I can understand job-related e-mails and spoken communication, and express myself clearly",
    "Native or bilingual proficiency",
]


# ---- match_option_locally (puro, sem LLM) ----


def test_exact_match():
    assert match_option_locally("Yes", ["No", "Yes", "Maybe"]) == "Yes"


def test_exact_match_case_and_space_insensitive():
    assert match_option_locally("  yes ", ["No", "Yes"]) == "Yes"


def test_startswith_option_contains_answer_prefix():
    # short answer, descriptive option starting with it
    opts = ["No, I am not authorized", "Yes, I am authorized to work"]
    assert match_option_locally("Yes", opts) == "Yes, I am authorized to work"


def test_startswith_answer_contains_option_prefix():
    # answer longer than the option
    assert match_option_locally("Yes, authorized", ["No", "Yes"]) == "Yes"


def test_startswith_respects_word_boundary():
    # 'No' must NOT match 'Not sure' (regression: naive startswith would match)
    assert match_option_locally("No", ["Not sure", "Nope"]) is None


def test_fuzzy_brasil_brazil():
    assert match_option_locally("Brasil", ["United States", "Brazil"]) == "Brazil"


def test_fuzzy_below_threshold_returns_none():
    # 'Fluent' has no textual overlap with CEFR phrases → local match fails (goes to the LLM)
    assert match_option_locally("Fluent", CEFR) is None


def test_empty_inputs_return_none():
    assert match_option_locally("", ["A", "B"]) is None
    assert match_option_locally("X", []) is None
