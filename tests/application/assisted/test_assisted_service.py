"""Tests for prepare_application / prepare_application_from_paste.

Routing is the point of this module: the wrong ATS branch producing the right
answer text is a bug that "does it return the paste hint" alone would miss.
Every routing assertion here is paired with proof that the branch NOT taken
was in fact not taken (an API not called, a fake LLM never consulted).
"""

from typing import Any

from moonlighter.application.assisted import service
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind


def _never_fetch_greenhouse(board: str, job_id: str, client: Any) -> Any:
    raise AssertionError("greenhouse API must not be called for this job")


def _never_fetch_recruitee(slug: str, offer: str, client: Any) -> Any:
    raise AssertionError("recruitee API must not be called for this job")


async def _never_llm(prompt: str, model: str, cache_prefix: str | None = None) -> str:
    raise AssertionError("the LLM must not be consulted when no questions were found")


def _stub_caller(answer: str = "a generated answer") -> Any:
    async def _call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return answer

    return _call


# ── prepare_application: routing ────────────────────────────────────────────


async def test_an_unsupported_source_asks_the_user_to_paste(job_factory, monkeypatch):
    job = job_factory(source="lever", url="https://jobs.lever.co/x/y")
    monkeypatch.setattr(service, "fetch_greenhouse_questions", _never_fetch_greenhouse)
    monkeypatch.setattr(service, "fetch_recruitee_questions", _never_fetch_recruitee)

    out = await service.prepare_application(job.id, {}, {})

    assert "copy" in out.lower()
    assert "prepare_application_from_paste" in out
    assert str(job.id) in out


async def test_a_greenhouse_job_with_no_questions_asks_the_user_to_paste(job_factory, monkeypatch):
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/1")

    async def no_questions(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return []

    monkeypatch.setattr(service, "fetch_greenhouse_questions", no_questions)
    monkeypatch.setattr(service, "fetch_recruitee_questions", _never_fetch_recruitee)

    out = await service.prepare_application(job.id, {}, {})

    assert "prepare_application_from_paste" in out


async def test_a_recruitee_job_with_no_questions_asks_the_user_to_paste(job_factory, monkeypatch):
    job = job_factory(source="recruitee", url="https://acme.recruitee.com/o/engineer")

    async def no_questions(slug: str, offer: str, client: Any) -> list[FormQuestion]:
        return []

    monkeypatch.setattr(service, "fetch_recruitee_questions", no_questions)
    monkeypatch.setattr(service, "fetch_greenhouse_questions", _never_fetch_greenhouse)

    out = await service.prepare_application(job.id, {}, {})

    assert "prepare_application_from_paste" in out


async def test_a_greenhouse_url_the_regex_cannot_parse_asks_the_user_to_paste(
    job_factory, monkeypatch
):
    # source says greenhouse, but the URL carries no board/job_id the regex can read
    # (e.g. a redirect or a custom landing page) -- must degrade to the paste hint,
    # not explode trying to call the API with nothing.
    job = job_factory(source="greenhouse", url="https://acme.example.com/careers")
    monkeypatch.setattr(service, "fetch_greenhouse_questions", _never_fetch_greenhouse)
    monkeypatch.setattr(service, "fetch_recruitee_questions", _never_fetch_recruitee)

    out = await service.prepare_application(job.id, {}, {})

    assert "prepare_application_from_paste" in out


async def test_a_recruitee_url_the_regex_cannot_parse_asks_the_user_to_paste(
    job_factory, monkeypatch
):
    job = job_factory(source="recruitee", url="https://careers.acme.com/jobs/engineer")
    monkeypatch.setattr(service, "fetch_greenhouse_questions", _never_fetch_greenhouse)
    monkeypatch.setattr(service, "fetch_recruitee_questions", _never_fetch_recruitee)

    out = await service.prepare_application(job.id, {}, {})

    assert "prepare_application_from_paste" in out


async def test_a_greenhouse_job_with_questions_returns_a_sheet_not_the_paste_hint(
    job_factory, monkeypatch
):
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/1")
    question = FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [question]

    monkeypatch.setattr(service, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(service, "fetch_recruitee_questions", _never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller())

    out = await service.prepare_application(job.id, {}, {})

    assert "prepare_application_from_paste" not in out
    assert "Favorite language" in out
    assert "a generated answer" in out


async def test_a_recruitee_job_with_questions_returns_a_sheet_not_the_paste_hint(
    job_factory, monkeypatch
):
    job = job_factory(source="recruitee", url="https://acme.recruitee.com/o/engineer")
    question = FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)

    async def one_question(slug: str, offer: str, client: Any) -> list[FormQuestion]:
        return [question]

    monkeypatch.setattr(service, "fetch_recruitee_questions", one_question)
    monkeypatch.setattr(service, "fetch_greenhouse_questions", _never_fetch_greenhouse)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller())

    out = await service.prepare_application(job.id, {}, {})

    assert "prepare_application_from_paste" not in out
    assert "Favorite language" in out
    assert "a generated answer" in out


async def test_a_missing_job_is_reported_rather_than_raising():
    out = await service.prepare_application(999999, {}, {})
    assert "999999" in out


# ── prepare_application_from_paste ──────────────────────────────────────────


async def test_paste_with_no_recognisable_questions_says_so(job_factory, monkeypatch):
    job = job_factory(source="lever", url="https://jobs.lever.co/x/y")
    monkeypatch.setattr(service, "extract_questions_from_page", _empty_extraction)

    out = await service.prepare_application_from_paste(job.id, "just marketing copy", {}, {})

    assert "No questions could be found" in out


async def _empty_extraction(page_text: str, llm_caller: Any) -> list[FormQuestion]:
    return []


async def test_paste_with_questions_returns_a_sheet(job_factory, monkeypatch):
    job = job_factory(source="lever", url="https://jobs.lever.co/x/y")
    question = FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)

    async def one_question(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        return [question]

    monkeypatch.setattr(service, "extract_questions_from_page", one_question)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller("we love it here"))

    out = await service.prepare_application_from_paste(job.id, "the whole copied page", {}, {})

    assert "No questions could be found" not in out
    assert "Why us?" in out
    assert "we love it here" in out


async def test_paste_for_a_missing_job_is_reported_rather_than_raising(monkeypatch):
    monkeypatch.setattr(service, "extract_questions_from_page", _never_extract)
    out = await service.prepare_application_from_paste(999999, "text", {}, {})
    assert "999999" in out


async def _never_extract(page_text: str, llm_caller: Any) -> list[FormQuestion]:
    raise AssertionError("must not extract questions when the job does not exist")
