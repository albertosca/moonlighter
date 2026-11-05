"""Loading the bank for replay: the question-to-answer map and the age cutoff."""

from datetime import timedelta

from moonlighter.application.answers.answer_bank import (
    list_entries,
    load_answer_bank,
    render_answer_bank,
)
from moonlighter.core.db import AnswerBankEntry, init_db

from tests.application.answers.answer_bank.bank_rows import FROZEN_NOW, aged_entry, dated_entry


def test_load_answer_bank_returns_normalized_question_to_answer_map(temporary_database):
    init_db()
    AnswerBankEntry.create(
        normalized_question="are you authorized to work in brazil",
        kind="boolean",
        answer="Yes",
        source_job_id=1,
    )
    assert load_answer_bank(maximum_age_days=None) == {
        "are you authorized to work in brazil": "Yes"
    }


def test_load_answer_bank_empty_table_returns_empty_dict(temporary_database):
    init_db()
    assert load_answer_bank(maximum_age_days=None) == {}


def test_load_answer_bank_skips_entries_older_than_max_age(temporary_database):
    # "When can you start?" gets banked like any boolean/text answer and would
    # replay verbatim months later. updated_at is refreshed on every promotion,
    # so age here means "since the last time this answer was actually used".
    init_db()
    aged_entry("when can you start", "in two weeks", days_old=91)
    aged_entry("notice period", "30 days", days_old=89)
    assert load_answer_bank(maximum_age_days=90) == {"notice period": "30 days"}


def test_load_answer_bank_with_no_max_age_keeps_everything(temporary_database):
    init_db()
    aged_entry("when can you start", "in two weeks", days_old=400)
    assert load_answer_bank(maximum_age_days=None) == {"when can you start": "in two weeks"}


def test_an_entry_exactly_at_the_age_limit_is_still_replayed(temporary_database, frozen_clock):
    init_db()
    dated_entry("notice period", "30 days", FROZEN_NOW - timedelta(days=90))
    dated_entry("when can you start", "in two weeks", FROZEN_NOW - timedelta(days=90, seconds=1))
    assert load_answer_bank(maximum_age_days=90) == {"notice period": "30 days"}
    lines = render_answer_bank(list_entries(), maximum_age_days=90).splitlines()
    assert lines[2].endswith("last used 2026-08-07]")
    assert lines[3].endswith("  (expired — not replayed)")
