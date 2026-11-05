"""The API over a paste, and the required-field hint when an ATS publishes no form."""

import httpx
import pytest
from moonlighter.application.assisted import service
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.required_labels import mark_required
from moonlighter.application.assisted.results import render_sheet_result
from moonlighter.application.assisted.sources import registry
from moonlighter.application.assisted.sources.base import SourceMatch

from tests.application.assisted.service.service_fakes import bypass_cv_bootstrap_offer, stub_caller


class _FakeSource:
    def __init__(self, name, url_part, *, questions=(), required=(), failure=None):
        self.name = name
        self._url_part = url_part
        self._questions = list(questions)
        self._required = tuple(required)
        self._failure = failure

    def match(self, job):
        return SourceMatch(self, (job.url,)) if self._url_part in job.url else None

    async def questions(self, match, client):
        if self._failure is not None:
            raise self._failure
        return self._questions

    async def required_fields(self, match, client):
        return self._required


async def test_needs_paste_lists_the_required_fields(job_factory, monkeypatch):
    job = job_factory(source="inhire", url="https://infleet.inhire.app/vagas/1")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(
        registry, "SOURCES", (_FakeSource("inhire", "inhire.app", required=("LinkedIn", "CV")),)
    )

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert "prepare_application_from_paste" in out
    assert "This form requires: LinkedIn, CV." in out


async def test_needs_paste_without_required_fields_is_unchanged(job_factory, monkeypatch):
    job = job_factory(source="inhire", url="https://infleet.inhire.app/vagas/1")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(registry, "SOURCES", (_FakeSource("inhire", "inhire.app"),))

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert out == service.PASTE_HINT.format(url=job.url, job_id=job.id)


async def test_paste_on_an_api_job_uses_the_api_and_says_so(job_factory, monkeypatch):
    job = job_factory(source="workable", url="https://apply.workable.com/j/ABC")
    bypass_cv_bootstrap_offer()
    api_question = FormQuestion(label="From the API", kind=QuestionKind.TEXT, required=True)
    monkeypatch.setattr(
        registry, "SOURCES", (_FakeSource("workable", "workable.com", questions=[api_question]),)
    )
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())

    async def never_extract(page_text, llm_caller, model="claude-sonnet-4-6"):
        raise AssertionError("the paste must not be read when the ATS publishes its form")

    monkeypatch.setattr(service, "extract_questions_from_page", never_extract)

    result = await service.prepare_application_from_paste(job.id, "Q1? Q2?", {}, profile={})

    assert [item.question.label for item in result.composed] == ["From the API"]
    assert result.source_note == service.SOURCE_NOTE_PASTE_IGNORED


async def test_paste_on_an_api_job_falls_back_to_the_paste_when_the_api_fails(
    job_factory, monkeypatch
):
    job = job_factory(source="workable", url="https://apply.workable.com/j/ABC")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(
        registry,
        "SOURCES",
        (_FakeSource("workable", "workable.com", failure=httpx.ConnectTimeout("slow")),),
    )
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())
    pasted = FormQuestion(label="From the paste", kind=QuestionKind.TEXT, required=False)

    async def extract(page_text, llm_caller, model="claude-sonnet-4-6"):
        return [pasted]

    monkeypatch.setattr(service, "extract_questions_from_page", extract)

    result = await service.prepare_application_from_paste(job.id, "Q1?", {}, profile={})

    assert [item.question.label for item in result.composed] == ["From the paste"]
    assert result.source_note is None


async def test_paste_on_inhire_marks_the_required_fields(job_factory, monkeypatch):
    job = job_factory(source="inhire", url="https://infleet.inhire.app/vagas/1")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(
        registry,
        "SOURCES",
        (
            _FakeSource(
                "inhire", "inhire.app", required=("LinkedIn", "Salary expectation", "CV", "cpf")
            ),
        ),
    )
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())
    extracted = [
        FormQuestion(label="Seu perfil no LinkedIn", kind=QuestionKind.TEXT, required=False),
        FormQuestion(label="Pretensão salarial", kind=QuestionKind.TEXT, required=False),
        FormQuestion(label="Anexe seu currículo", kind=QuestionKind.FILE, required=False),
        FormQuestion(label="Conte sobre você", kind=QuestionKind.LONG_TEXT, required=False),
        FormQuestion(label="OpenCV experience", kind=QuestionKind.TEXT, required=False),
        FormQuestion(label="Nome completo", kind=QuestionKind.TEXT, required=True),
        FormQuestion(label="Seu CPF", kind=QuestionKind.TEXT, required=False),
    ]

    async def extract(page_text, llm_caller, model="claude-sonnet-4-6"):
        return extracted

    monkeypatch.setattr(service, "extract_questions_from_page", extract)

    result = await service.prepare_application_from_paste(job.id, "page", {}, profile={})

    required = {item.question.label: item.question.required for item in result.composed}
    assert required == {
        "Seu perfil no LinkedIn": True,
        "Pretensão salarial": True,
        "Anexe seu currículo": True,
        "Conte sobre você": False,
        "OpenCV experience": False,  # "cv" inside "OpenCV" is not the word "cv"
        "Nome completo": True,  # already required stays required
        "Seu CPF": True,  # an unknown required id matches by its own name
    }


@pytest.mark.parametrize(
    ("required_label", "form_label"),
    [
        ("Salary expectation", "Expectativa salarial"),
        ("Salary expectation", "Remuneração pretendida"),
        ("Salary expectation", "Remuneracao desejada"),
        ("CV", "Upload your résumé"),
    ],
)
def test_required_ids_match_their_common_portuguese_and_accented_wordings(
    required_label, form_label
):
    question = FormQuestion(label=form_label, kind=QuestionKind.TEXT, required=False)
    [marked] = mark_required([question], (required_label,))
    assert marked.required is True
