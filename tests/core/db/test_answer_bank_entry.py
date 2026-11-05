"""AnswerBankEntry stores an approved answer under its normalized question, and that question is unique."""

import pytest
from peewee import IntegrityError

from moonlighter.core.db import AnswerBankEntry, init_db


def test_answer_bank_entry_created_and_normalized_question_is_unique(temporary_database):
    init_db()
    AnswerBankEntry.create(
        normalized_question="do you have 5 years of python experience",
        kind="boolean",
        answer="Yes",
        source_job_id=1,
    )
    row = AnswerBankEntry.get(
        AnswerBankEntry.normalized_question == "do you have 5 years of python experience"
    )
    assert row.answer == "Yes"
    assert row.source_job_id == 1
    assert row.updated_at is not None
    with pytest.raises(IntegrityError):
        AnswerBankEntry.create(
            normalized_question="do you have 5 years of python experience",
            kind="boolean",
            answer="No",
            source_job_id=2,
        )
