"""Label cleaning: the decoration a form hangs on a label never hides the rule behind it."""

from moonlighter.application.answers.field_map import pre_populate_answers

from tests.application.answers.candidate_profiles import PROFILE


def test_a_trailing_colon_or_parenthesised_marker_does_not_hide_a_rule():
    """2026-09-29 review: "Name:" and "Name (required)" went unmatched while
    "Name *" matched. The shared label cleaning now drops them too, so every
    rule gains, not just the name one.
    """
    cases = {
        "Name:": "Maria de Souza Pereira",
        "Name (required)": "Maria de Souza Pereira",
        "Email:": "maria.pereira@example.com",
        "Phone (required)": "11912345678",
        "Nome completo (obrigatório)": "Maria de Souza Pereira",
    }
    for label, expected in cases.items():
        assert pre_populate_answers([label], PROFILE).get(label) == expected, label


def test_strips_asterisk_from_label():
    result = pre_populate_answers(["Phone *"], PROFILE)
    assert result["Phone *"] == "11912345678"


def test_ptbr_strips_asterisk():
    result = pre_populate_answers(["Telefone*", "Nome*", "Sobrenome*"], PROFILE)
    assert result["Telefone*"] == "11912345678"
    assert result["Nome*"] == "Maria"
    assert result["Sobrenome*"] == "de Souza Pereira"


# ── label normalisation ───────────────────────────────────────────────────────


def test_required_marker_on_its_own_line_does_not_break_matching():
    r"""Workable renders the required marker as a line BEFORE the label, so the
    scraped string is '*\nFirst name'. Every rule here is ^-anchored, so nothing
    matched and the name, phone and email were left for the LLM to guess —
    including the tracking alias field, which must never be guessed. Observed on
    a live Workable posting, 2026-08-04.
    """
    result = pre_populate_answers(["*\nFirst name", "*\nLast name"], PROFILE)
    assert result["*\nFirst name"] == "Maria"
    assert result["*\nLast name"] == "de Souza Pereira"


def test_trailing_country_code_line_does_not_break_matching():
    r"""'*\nPhone\n+55' — the country code is appended on its own line."""
    result = pre_populate_answers(["*\nPhone\n+55"], PROFILE)
    assert result["*\nPhone\n+55"] == "11912345678"


def test_email_label_with_a_leading_marker_is_still_deterministic():
    result = pre_populate_answers(["*\nEmail"], PROFILE)
    assert result["*\nEmail"] == "maria.pereira@example.com"


def test_normalisation_does_not_swallow_a_real_multi_line_question():
    """Only a bare marker line is dropped. A label whose first line is real text
    keeps it — collapsing everything would let unrelated rules match.
    """
    label = "Why do you want to work here?\nPlease be specific."
    assert label not in pre_populate_answers([label], PROFILE)
