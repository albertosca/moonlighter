"""prepare_application_from_paste: what it says when the reading fails or finds nothing, and the sheet it builds."""

from typing import Any

from moonlighter.application.assisted import service
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sheet.results import render_sheet_result
from moonlighter.application.assisted.sources.pasted import ExtractionError

from tests.application.assisted.service.service_fakes import (
    bypass_cv_bootstrap_offer,
    never_extract,
    stub_caller,
)


async def test_paste_with_no_recognisable_questions_says_so(job_factory, monkeypatch):
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(service, "extract_questions_from_page", _empty_extraction)

    out = render_sheet_result(
        await service.prepare_application_from_paste(job.id, "just marketing copy", {}, profile={})
    )

    assert "No questions could be found" in out


async def test_paste_whose_reading_failed_says_so_instead_of_blaming_the_paste(
    job_factory, monkeypatch
):
    """An unparseable model reply used to surface as "Was the whole page copied?"."""
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    bypass_cv_bootstrap_offer()

    async def failed_extraction(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        raise ExtractionError("the model's reply was not JSON: sorry")

    monkeypatch.setattr(service, "extract_questions_from_page", failed_extraction)
    out = render_sheet_result(
        await service.prepare_application_from_paste(
            job.id, "the whole copied page", {}, profile={}
        )
    )
    assert "Was the whole page copied" not in out
    assert "run it again" in out


async def _empty_extraction(page_text: str, llm_caller: Any) -> list[FormQuestion]:
    return []


async def test_paste_with_questions_returns_a_sheet(job_factory, monkeypatch):
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    bypass_cv_bootstrap_offer()
    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)

    async def one_question(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        return [question]

    monkeypatch.setattr(service, "extract_questions_from_page", one_question)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller("we love it here"))

    out = render_sheet_result(
        await service.prepare_application_from_paste(
            job.id, "the whole copied page", {}, profile={}
        )
    )

    assert "No questions could be found" not in out
    assert "Why us?" in out
    assert "we love it here" in out


async def test_paste_for_a_missing_job_is_reported_rather_than_raising(monkeypatch):
    monkeypatch.setattr(service, "extract_questions_from_page", never_extract)
    out = render_sheet_result(
        await service.prepare_application_from_paste(999999, "text", {}, profile={})
    )
    assert "999999" in out
