"""list_answer_bank shows what would be replayed and forget_answer removes it."""

from moonlighter.core.db import AnswerBankEntry, init_db
from moonlighter.mcp_tools.answer_bank import forget_answer, list_answer_bank
from tests._context import make_test_context


async def test_list_answer_bank_shows_what_would_be_replayed(temporary_database):
    init_db()

    AnswerBankEntry.create(
        normalized_question="notice period", kind="text", answer="30 days", source_job_id=7
    )
    result = await list_answer_bank(
        context=make_test_context(config={"answer_bank_max_age_days": 90})
    )
    assert "notice period" in result
    assert "30 days" in result


async def test_list_answer_bank_empty(temporary_database):
    init_db()

    result = await list_answer_bank(context=make_test_context(config={}))
    assert result == "The answer bank is empty."


async def test_forget_answer_removes_the_entry_and_says_so(temporary_database):
    init_db()

    AnswerBankEntry.create(
        normalized_question="notice period", kind="text", answer="30 days", source_job_id=7
    )
    result = await forget_answer("Notice period?")
    assert "notice period" in result
    assert AnswerBankEntry.select().count() == 0


async def test_forget_answer_reports_no_match(temporary_database):
    init_db()

    result = await forget_answer("nothing here")
    assert "No banked answer" in result
