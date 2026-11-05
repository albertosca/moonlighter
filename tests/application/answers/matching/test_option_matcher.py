from moonlighter.application.answers.matching.option_matcher import (
    _starts_with_word,
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
    options = ["No, I am not authorized", "Yes, I am authorized to work"]
    assert match_option_locally("Yes", options) == "Yes, I am authorized to work"


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


def test_starts_with_word_equal_strings_is_boundary_match():
    # Direct helper contract: an exact-length prefix is a word-boundary match.
    # Unreachable through match_option_locally (the exact path wins first),
    # but the helper's own contract must hold for any future caller.
    assert _starts_with_word("brazil", "brazil") is True


# ---- characterization pins: order, tie-break, threshold boundary and default ----


def test_exact_match_returns_the_first_option_that_normalises_alike():
    assert match_option_locally("YES", ["yes", "Yes"]) == "yes"


def test_prefix_match_returns_the_first_option_that_qualifies():
    assert match_option_locally("Yes", ["Yes, remote", "Yes, on site"]) == "Yes, remote"


def test_fuzzy_tie_keeps_the_first_best_option():
    # "abcx" and "abcy" both score 0.75 against "abcd": a strictly greater score is
    # needed to displace the first.
    assert match_option_locally("abcd", ["abcx", "abcy"], threshold=0.7) == "abcx"


def test_fuzzy_score_equal_to_the_threshold_is_accepted():
    assert match_option_locally("abcd", ["abce"], threshold=0.75) == "abce"
    assert match_option_locally("abcd", ["abce"], threshold=0.76) is None


def test_default_threshold_accepts_0_8_and_refuses_0_75():
    assert match_option_locally("abcde", ["abcdf"]) == "abcdf"
    assert match_option_locally("abcd", ["abce"]) is None


def test_a_none_answer_is_treated_as_empty():
    assert match_option_locally(None, ["A", "B"]) is None


def test_an_exact_match_beats_an_earlier_prefix_match():
    assert match_option_locally("Yes", ["Yes, remote", "Yes"]) == "Yes"


def test_a_prefix_match_beats_an_earlier_fuzzy_match():
    # "yess" scores 0.857 against "yes", above the default threshold.
    assert match_option_locally("Yes", ["Yess", "Yes, remote"]) == "Yes, remote"
