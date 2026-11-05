"""Promoting an application's answers into the bank: what is banked, skipped or overwritten."""

import pytest
from moonlighter.application.answers.bank.store import promote_application
from moonlighter.core.db import AnswerBankEntry, init_db

from tests.application.answers.bank.store.bank_rows import FROZEN_NOW, JANUARY_SECOND, dated_entry


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


def test_promote_application_overwrite_refreshes_kind_and_last_use(
    temporary_database, frozen_clock
):
    init_db()
    dated_entry("notice period", "30 days", JANUARY_SECOND)
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
