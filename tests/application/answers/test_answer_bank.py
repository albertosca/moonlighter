import pytest
from moonlighter.application.answers.answer_bank import (
    is_bank_eligible,
    is_sensitive_label,
    load_answer_bank,
    normalize_question,
    promote_application,
)
from moonlighter.application.assisted.questions import QuestionKind
from moonlighter.core.db import AnswerBankEntry, init_db

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
        "Do you have 5+ years of Python experience?",
        "Why do you want to work here?",
        "Notice period",
    ],
)
def test_is_sensitive_label_false_for_ordinary_screening_questions(label):
    assert is_sensitive_label(label) is False


# ── load_answer_bank ──────────────────────────────────────────────────────────


def test_load_answer_bank_returns_normalized_question_to_answer_map(tmp_db):
    init_db()
    AnswerBankEntry.create(
        normalized_question="are you authorized to work in brazil",
        kind="boolean",
        answer="Yes",
        source_job_id=1,
    )
    assert load_answer_bank() == {"are you authorized to work in brazil": "Yes"}


def test_load_answer_bank_empty_table_returns_empty_dict(tmp_db):
    init_db()
    assert load_answer_bank() == {}


# ── promote_application ───────────────────────────────────────────────────────


def test_promote_application_creates_a_new_entry(tmp_db):
    init_db()
    job_cache = {"Are you authorized to work in Brazil?": {"answer": "Yes", "kind": "boolean"}}
    promote_application(job_cache, source_job_id=42)
    row = AnswerBankEntry.get(
        AnswerBankEntry.normalized_question == "are you authorized to work in brazil"
    )
    assert row.answer == "Yes"
    assert row.kind == "boolean"
    assert row.source_job_id == 42


def test_promote_application_skips_long_text(tmp_db):
    init_db()
    job_cache = {"Why do you want to work here?": {"answer": "a custom essay", "kind": "long_text"}}
    promote_application(job_cache, source_job_id=1)
    assert AnswerBankEntry.select().count() == 0


def test_promote_application_overwrites_an_existing_entry(tmp_db):
    init_db()
    AnswerBankEntry.create(
        normalized_question="are you authorized to work in brazil",
        kind="boolean",
        answer="No",
        source_job_id=1,
    )
    job_cache = {"Are you authorized to work in Brazil?": {"answer": "Yes", "kind": "boolean"}}
    promote_application(job_cache, source_job_id=2)
    row = AnswerBankEntry.get(
        AnswerBankEntry.normalized_question == "are you authorized to work in brazil"
    )
    assert row.answer == "Yes"
    assert row.source_job_id == 2


def test_promote_application_ignores_legacy_flat_shaped_entries(tmp_db):
    # tests/test_server.py's create_application() fixture defaults form_data to
    # '{"Q": "A"}' — a flat label->string shape that predates this feature and is
    # used by many unrelated update_status tests. promote_application must not
    # crash when it sees this shape; it must simply skip it.
    init_db()
    promote_application({"Q": "A"}, source_job_id=1)
    assert AnswerBankEntry.select().count() == 0


@pytest.mark.parametrize("label", ["Gender", "Veteran Status", "References"])
def test_promote_application_skips_a_sensitive_label(tmp_db, label):
    # Kind alone does not protect these: a demographic or references question is
    # usually TEXT, which IS bank-eligible. Nothing deterministic stops the LLM
    # guessing an answer to such a label, and a guess must not be replayed at
    # every future company from a shared table.
    init_db()
    promote_application({label: {"answer": "a guess", "kind": "text"}}, source_job_id=1)
    assert AnswerBankEntry.select().count() == 0


def test_promote_application_ignores_invalid_kind(tmp_db):
    init_db()
    job_cache = {"A question": {"answer": "some answer", "kind": "invalid_kind"}}
    promote_application(job_cache, source_job_id=1)
    assert AnswerBankEntry.select().count() == 0
