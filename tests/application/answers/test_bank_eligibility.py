"""The bank's pure gatekeeping: question normalisation, eligible kinds and sensitive labels."""

import pytest
from moonlighter.application.answers.bank_eligibility import (
    is_bank_eligible,
    is_sensitive_label,
    normalize_question,
)
from moonlighter.application.assisted.questions import QuestionKind

# ── normalize_question ───────────────────────────────────────────────────────


def test_normalize_question_lowercases_collapses_whitespace_and_strips_trailing_punctuation():
    assert normalize_question("  Are You   Legally Authorized ?  ") == "are you legally authorized"


def test_normalize_question_strips_trailing_colon_and_asterisk():
    assert normalize_question("Full name:*") == "full name"


# ── is_bank_eligible ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kind",
    [
        QuestionKind.TEXT,
        QuestionKind.BOOLEAN,
        QuestionKind.SINGLE_SELECT,
        QuestionKind.MULTI_SELECT,
    ],
)
def test_is_bank_eligible_true_for_eligible_kinds(kind):
    assert is_bank_eligible(kind) is True


@pytest.mark.parametrize("kind", [QuestionKind.LONG_TEXT, QuestionKind.FILE])
def test_is_bank_eligible_false_for_ineligible_kinds(kind):
    assert is_bank_eligible(kind) is False


# ── is_sensitive_label ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "label",
    [
        "Gender",
        "What is your gender identity?",
        "Race / Ethnicity",
        "Raça/Cor",
        "Are you Hispanic or Latino?",
        "Veteran Status",
        "Disability status",
        "Pessoa com deficiência?",
        "References",
        "Please provide a professional reference",
        "Referências profissionais",
    ],
)
def test_is_sensitive_label_true_for_demographics_and_references(label):
    assert is_sensitive_label(label) is True


@pytest.mark.parametrize(
    "label",
    [
        # Categories the first version of this regex missed. Each one reached the
        # LLM, got a hallucinated answer, and — because promote_application's own
        # check uses this same function — was banked and replayed at the next
        # company. "Ethnicity" is the one that made this concrete: a real Greenhouse
        # label, and the full leak path was open for it.
        "Ethnicity",
        "Etnia",
        "What are your pronouns?",
        "Pronomes",
        "Sexual orientation",
        "Orientação sexual",
        "Age",
        "Idade",
        "Date of birth",
        "Data de nascimento",
        "Marital status",
        "Estado civil",
        "Religion",
        "Religião",
        "Are you a member of the LGBTQ+ community?",
    ],
)
def test_is_sensitive_label_true_for_the_wider_demographic_set(label):
    assert is_sensitive_label(label) is True


@pytest.mark.parametrize(
    "label",
    [
        "Do you have 5+ years of Python experience?",
        "Why do you want to work here?",
        "Notice period",
        # Measured near-misses of the wider set. Without word boundaries,
        # "pronoun" swallows "pronounce" and "idade" swallows "Cidade" — both real
        # fields, and the city one is answered by field_map today.
        "How do you pronounce your name?",
        "Localização (Cidade)",
        "Cidade",
        "What is your average deal size?",
        "Page load performance experience",
        "Percentage of time on-call",
    ],
)
def test_is_sensitive_label_false_for_ordinary_screening_questions(label):
    assert is_sensitive_label(label) is False


@pytest.mark.parametrize("label", ["Preferências de horário", "What is your age?", "Age (years)"])
def test_is_sensitive_label_pins_the_deliberate_over_match_and_the_age_word(label):
    assert is_sensitive_label(label) is True
