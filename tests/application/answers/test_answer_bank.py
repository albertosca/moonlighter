from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from moonlighter.application.answers import answer_bank
from moonlighter.application.answers.answer_bank import (
    forget,
    is_bank_eligible,
    is_sensitive_label,
    list_entries,
    load_answer_bank,
    normalize_question,
    promote_application,
    render_answer_bank,
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


# ── load_answer_bank ──────────────────────────────────────────────────────────


def test_load_answer_bank_returns_normalized_question_to_answer_map(temporary_database):
    init_db()
    AnswerBankEntry.create(
        normalized_question="are you authorized to work in brazil",
        kind="boolean",
        answer="Yes",
        source_job_id=1,
    )
    assert load_answer_bank(max_age_days=None) == {"are you authorized to work in brazil": "Yes"}


def test_load_answer_bank_empty_table_returns_empty_dict(temporary_database):
    init_db()
    assert load_answer_bank(max_age_days=None) == {}


# ── promote_application ───────────────────────────────────────────────────────


def test_promote_application_creates_a_new_entry(temporary_database):
    init_db()
    job_cache = {"Are you authorized to work in Brazil?": {"answer": "Yes", "kind": "boolean"}}
    promote_application(job_cache, source_job_id=42)
    row = AnswerBankEntry.get(
        AnswerBankEntry.normalized_question == "are you authorized to work in brazil"
    )
    assert row.answer == "Yes"
    assert row.kind == "boolean"
    assert row.source_job_id == 42


def test_promote_application_skips_long_text(temporary_database):
    init_db()
    job_cache = {"Why do you want to work here?": {"answer": "a custom essay", "kind": "long_text"}}
    promote_application(job_cache, source_job_id=1)
    assert AnswerBankEntry.select().count() == 0


def test_promote_application_overwrites_an_existing_entry(temporary_database):
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


def test_promote_application_ignores_legacy_flat_shaped_entries(temporary_database):
    # tests/test_server.py's create_application() fixture defaults form_data to
    # '{"Q": "A"}' — a flat label->string shape that predates this feature and is
    # used by many unrelated update_status tests. promote_application must not
    # crash when it sees this shape; it must simply skip it.
    init_db()
    promote_application({"Q": "A"}, source_job_id=1)
    assert AnswerBankEntry.select().count() == 0


@pytest.mark.parametrize("label", ["Gender", "Veteran Status", "References"])
def test_promote_application_skips_a_sensitive_label(temporary_database, label):
    # Kind alone does not protect these: a demographic or references question is
    # usually TEXT, which IS bank-eligible. Nothing deterministic stops the LLM
    # guessing an answer to such a label, and a guess must not be replayed at
    # every future company from a shared table.
    init_db()
    promote_application({label: {"answer": "a guess", "kind": "text"}}, source_job_id=1)
    assert AnswerBankEntry.select().count() == 0


def test_promote_application_ignores_invalid_kind(temporary_database):
    init_db()
    job_cache = {"A question": {"answer": "some answer", "kind": "invalid_kind"}}
    promote_application(job_cache, source_job_id=1)
    assert AnswerBankEntry.select().count() == 0


# ── expiry ────────────────────────────────────────────────────────────────────


def _entry(question: str, answer: str, days_old: int) -> None:
    from datetime import datetime, timedelta

    AnswerBankEntry.create(
        normalized_question=question,
        kind="text",
        answer=answer,
        source_job_id=1,
        updated_at=datetime.now() - timedelta(days=days_old),
    )


def test_load_answer_bank_skips_entries_older_than_max_age(temporary_database):
    # "When can you start?" gets banked like any boolean/text answer and would
    # replay verbatim months later. updated_at is refreshed on every promotion,
    # so age here means "since the last time this answer was actually used".
    init_db()
    _entry("when can you start", "in two weeks", days_old=91)
    _entry("notice period", "30 days", days_old=89)
    assert load_answer_bank(max_age_days=90) == {"notice period": "30 days"}


def test_load_answer_bank_with_no_max_age_keeps_everything(temporary_database):
    init_db()
    _entry("when can you start", "in two weeks", days_old=400)
    assert load_answer_bank(max_age_days=None) == {"when can you start": "in two weeks"}


# ── inspection and editing ────────────────────────────────────────────────────


def test_list_entries_returns_rows_most_recently_used_first(temporary_database):
    init_db()
    _entry("notice period", "30 days", days_old=5)
    _entry("when can you start", "in two weeks", days_old=1)
    assert [row.normalized_question for row in list_entries()] == [
        "when can you start",
        "notice period",
    ]


def test_forget_normalises_the_question_and_deletes_the_row(temporary_database):
    init_db()
    _entry("are you authorized to work in brazil", "Yes", days_old=1)
    assert forget("  Are You Authorized to Work in Brazil?  ") is True
    assert AnswerBankEntry.select().count() == 0


def test_forget_reports_when_nothing_matched(temporary_database):
    init_db()
    _entry("notice period", "30 days", days_old=1)
    assert forget("something else") is False
    assert AnswerBankEntry.select().count() == 1


def test_render_answer_bank_marks_entries_past_max_age(temporary_database):
    # The operator's real question is "why wasn't this replayed?" — the
    # listing answers it inline instead of making them do date arithmetic.
    init_db()
    _entry("notice period", "30 days", days_old=5)
    _entry("when can you start", "in two weeks", days_old=120)
    out = render_answer_bank(list_entries(), max_age_days=90)
    assert "notice period" in out and "30 days" in out
    assert "when can you start" in out and "in two weeks" in out
    stale_line = next(line for line in out.splitlines() if "when can you start" in line)
    fresh_line = next(line for line in out.splitlines() if "notice period" in line)
    assert "expired" in stale_line
    assert "expired" not in fresh_line


def test_render_answer_bank_empty(temporary_database):
    init_db()
    assert render_answer_bank([], max_age_days=90) == "The answer bank is empty."


# ── characterization pins: exact rendering, overwrite and the expiry boundary ──

FROZEN_NOW = datetime(2026, 11, 5, 12, 0, 0)  # noqa: DTZ001 - the database stores naive local time
SEPTEMBER_FIRST = FROZEN_NOW - timedelta(days=65)
JANUARY_SECOND = FROZEN_NOW - timedelta(days=307)


@pytest.fixture
def frozen_clock(monkeypatch):
    """Answer-bank time stands still at FROZEN_NOW, so a boundary can be exact."""
    monkeypatch.setattr(answer_bank, "datetime", SimpleNamespace(now=lambda: FROZEN_NOW))


def _dated_entry(question: str, answer: str, updated_at: datetime, *, kind: str = "text") -> None:
    AnswerBankEntry.create(
        normalized_question=question,
        kind=kind,
        answer=answer,
        source_job_id=1,
        updated_at=updated_at,
    )


def test_render_answer_bank_exact_text_for_one_entry(temporary_database, frozen_clock):
    init_db()
    _dated_entry("notice period", "30 days", SEPTEMBER_FIRST)
    assert render_answer_bank(list_entries(), max_age_days=90) == (
        "# Answer bank — 1 entry\n\n- **notice period** → 30 days  [text, job #1, last used 2026-09-01]"
    )


def test_render_answer_bank_exact_text_for_entries_with_an_expired_one(
    temporary_database, frozen_clock
):
    init_db()
    _dated_entry("notice period", "30 days", SEPTEMBER_FIRST)
    _dated_entry("when can you start", "in two weeks", JANUARY_SECOND, kind="single_select")
    assert render_answer_bank(list_entries(), max_age_days=90) == (
        "# Answer bank — 2 entries\n\n"
        "- **notice period** → 30 days  [text, job #1, last used 2026-09-01]\n"
        "- **when can you start** → in two weeks  [single_select, job #1, last used 2026-01-02]"
        "  (expired — not replayed)"
    )


def test_an_entry_exactly_at_the_age_limit_is_still_replayed(temporary_database, frozen_clock):
    init_db()
    _dated_entry("notice period", "30 days", FROZEN_NOW - timedelta(days=90))
    _dated_entry("when can you start", "in two weeks", FROZEN_NOW - timedelta(days=90, seconds=1))
    assert load_answer_bank(max_age_days=90) == {"notice period": "30 days"}
    lines = render_answer_bank(list_entries(), max_age_days=90).splitlines()
    assert lines[2].endswith("last used 2026-08-07]")
    assert lines[3].endswith("  (expired — not replayed)")


def test_promote_application_overwrite_refreshes_kind_and_last_use(
    temporary_database, frozen_clock
):
    init_db()
    _dated_entry("notice period", "30 days", JANUARY_SECOND)
    job_cache = {"Notice period": {"answer": "60 days", "kind": "single_select"}}
    promote_application(job_cache, source_job_id=3)
    row = AnswerBankEntry.get(AnswerBankEntry.normalized_question == "notice period")
    assert row.kind == "single_select"
    assert row.updated_at == FROZEN_NOW


def test_two_labels_that_normalise_alike_bank_one_row_with_the_last_answer(temporary_database):
    init_db()
    job_cache = {
        "Notice period?": {"answer": "30 days", "kind": "text"},
        "  notice   PERIOD:": {"answer": "60 days", "kind": "text"},
    }
    promote_application(job_cache, source_job_id=4)
    rows = list(AnswerBankEntry.select())
    assert [(row.normalized_question, row.answer) for row in rows] == [("notice period", "60 days")]
