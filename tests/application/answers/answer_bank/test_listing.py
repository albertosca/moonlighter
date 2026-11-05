"""Inspecting and editing the bank: listing order, forgetting a row and the rendered listing."""

from moonlighter.application.answers.answer_bank import forget, list_entries, render_answer_bank
from moonlighter.core.db import AnswerBankEntry, init_db

from tests.application.answers.answer_bank.bank_rows import (
    JANUARY_SECOND,
    SEPTEMBER_FIRST,
    aged_entry,
    dated_entry,
)


def test_list_entries_returns_rows_most_recently_used_first(temporary_database):
    init_db()
    aged_entry("notice period", "30 days", days_old=5)
    aged_entry("when can you start", "in two weeks", days_old=1)
    assert [row.normalized_question for row in list_entries()] == [
        "when can you start",
        "notice period",
    ]


def test_forget_normalises_the_question_and_deletes_the_row(temporary_database):
    init_db()
    aged_entry("are you authorized to work in brazil", "Yes", days_old=1)
    assert forget("  Are You Authorized to Work in Brazil?  ") is True
    assert AnswerBankEntry.select().count() == 0


def test_forget_reports_when_nothing_matched(temporary_database):
    init_db()
    aged_entry("notice period", "30 days", days_old=1)
    assert forget("something else") is False
    assert AnswerBankEntry.select().count() == 1


def test_render_answer_bank_marks_entries_past_max_age(temporary_database):
    # The operator's real question is "why wasn't this replayed?" — the
    # listing answers it inline instead of making them do date arithmetic.
    init_db()
    aged_entry("notice period", "30 days", days_old=5)
    aged_entry("when can you start", "in two weeks", days_old=120)
    out = render_answer_bank(list_entries(), maximum_age_days=90)
    assert "notice period" in out
    assert "30 days" in out
    assert "when can you start" in out
    assert "in two weeks" in out
    stale_line = next(line for line in out.splitlines() if "when can you start" in line)
    fresh_line = next(line for line in out.splitlines() if "notice period" in line)
    assert "expired" in stale_line
    assert "expired" not in fresh_line


def test_render_answer_bank_empty(temporary_database):
    init_db()
    assert render_answer_bank([], maximum_age_days=90) == "The answer bank is empty."


def test_render_answer_bank_exact_text_for_one_entry(temporary_database, frozen_clock):
    init_db()
    dated_entry("notice period", "30 days", SEPTEMBER_FIRST)
    assert render_answer_bank(list_entries(), maximum_age_days=90) == (
        "# Answer bank — 1 entry\n\n- **notice period** → 30 days  [text, job #1, last used 2026-09-01]"
    )


def test_render_answer_bank_exact_text_for_entries_with_an_expired_one(
    temporary_database, frozen_clock
):
    init_db()
    dated_entry("notice period", "30 days", SEPTEMBER_FIRST)
    dated_entry("when can you start", "in two weeks", JANUARY_SECOND, kind="single_select")
    assert render_answer_bank(list_entries(), maximum_age_days=90) == (
        "# Answer bank — 2 entries\n\n"
        "- **notice period** → 30 days  [text, job #1, last used 2026-09-01]\n"
        "- **when can you start** → in two weeks  [single_select, job #1, last used 2026-01-02]"
        "  (expired — not replayed)"
    )
