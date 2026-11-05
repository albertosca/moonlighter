"""Routing: each job takes the right ATS branch, and the branch not taken is proven untouched."""

from typing import Any

from moonlighter.application.assisted import service
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sheet.results import render_sheet_result
from moonlighter.application.assisted.sources import greenhouse as greenhouse_source
from moonlighter.application.assisted.sources import recruitee as recruitee_source

from tests.application.assisted.service.service_fakes import (
    bypass_cv_bootstrap_offer,
    never_fetch_greenhouse,
    never_fetch_recruitee,
    stub_caller,
)


async def test_an_unsupported_source_asks_the_user_to_paste(job_factory, monkeypatch):
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", never_fetch_greenhouse)
    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", never_fetch_recruitee)

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert "copy" in out.lower()
    assert "prepare_application_from_paste" in out
    assert str(job.id) in out


async def test_a_greenhouse_job_with_no_questions_asks_the_user_to_paste(job_factory, monkeypatch):
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/1")
    bypass_cv_bootstrap_offer()

    async def no_questions(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return []

    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", no_questions)
    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", never_fetch_recruitee)

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert "prepare_application_from_paste" in out


async def test_a_recruitee_job_with_no_questions_asks_the_user_to_paste(job_factory, monkeypatch):
    job = job_factory(source="recruitee", url="https://acme.recruitee.com/o/engineer")
    bypass_cv_bootstrap_offer()

    async def no_questions(slug: str, offer: str, client: Any) -> list[FormQuestion]:
        return []

    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", no_questions)
    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", never_fetch_greenhouse)

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert "prepare_application_from_paste" in out


async def test_a_greenhouse_url_the_regex_cannot_parse_asks_the_user_to_paste(
    job_factory, monkeypatch
):
    # source says greenhouse, but the URL carries no board/job_id the regex can read
    # (e.g. a redirect or a custom landing page) -- must degrade to the paste hint,
    # not explode trying to call the API with nothing.
    job = job_factory(source="greenhouse", url="https://acme.example.com/careers")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", never_fetch_greenhouse)
    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", never_fetch_recruitee)

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert "prepare_application_from_paste" in out


async def test_a_recruitee_url_the_regex_cannot_parse_asks_the_user_to_paste(
    job_factory, monkeypatch
):
    job = job_factory(source="recruitee", url="https://careers.acme.com/jobs/engineer")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", never_fetch_greenhouse)
    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", never_fetch_recruitee)

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert "prepare_application_from_paste" in out


async def test_a_greenhouse_job_with_questions_returns_a_sheet_not_the_paste_hint(
    job_factory, monkeypatch
):
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/1")
    bypass_cv_bootstrap_offer()
    question = FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [question]

    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller("a generated answer"))

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert "prepare_application_from_paste" not in out
    assert "Favorite language" in out
    assert "a generated answer" in out


async def test_a_recruitee_job_with_questions_returns_a_sheet_not_the_paste_hint(
    job_factory, monkeypatch
):
    job = job_factory(source="recruitee", url="https://acme.recruitee.com/o/engineer")
    bypass_cv_bootstrap_offer()
    question = FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)

    async def one_question(slug: str, offer: str, client: Any) -> list[FormQuestion]:
        return [question]

    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", one_question)
    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", never_fetch_greenhouse)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller("a generated answer"))

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert "prepare_application_from_paste" not in out
    assert "Favorite language" in out
    assert "a generated answer" in out


async def test_a_missing_job_is_reported_rather_than_raising():
    out = render_sheet_result(await service.prepare_application(999999, {}, {}))
    assert "999999" in out
