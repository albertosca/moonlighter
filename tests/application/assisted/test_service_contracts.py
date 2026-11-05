"""Pins for what the assisted service hands to its collaborators, and the words it says."""

import logging
from typing import Any

import httpx
import pytest
from moonlighter.application.assisted import service
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.results import SheetKind
from moonlighter.application.assisted.sources import greenhouse as greenhouse_source
from moonlighter.application.assisted.sources.pasted import ExtractionError
from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.db import record_cv_bootstrap_decline

GREENHOUSE_URL = "https://job-boards.greenhouse.io/acme/jobs/1"
QUESTION = FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)


async def _stub_caller_for(prompt: str, model: str, cache_prefix: str | None = None) -> str:
    return "an answer"


async def _one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
    return [QUESTION]


async def _no_questions(board: str, job_id: str, client: Any) -> list[FormQuestion]:
    return []


def _greenhouse_job(job_factory: Any, **overrides: Any) -> Any:
    record_cv_bootstrap_decline()
    return job_factory(source="greenhouse", url=GREENHOUSE_URL, **overrides)


async def test_the_ats_is_asked_with_a_twenty_second_timeout(job_factory, monkeypatch):
    seen: dict[str, Any] = {}

    class SpyClient(httpx.AsyncClient):
        def __init__(self, **options: Any) -> None:
            seen.update(options)
            super().__init__(**options)

    job = job_factory(source="greenhouse", url=GREENHOUSE_URL)
    record_cv_bootstrap_decline()
    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", _no_questions)
    monkeypatch.setattr(service.httpx, "AsyncClient", SpyClient)

    await service.prepare_application(job.id, {}, {})

    assert seen == {"timeout": 20}


async def test_the_collaborators_receive_exactly_the_job_fields_they_read(job_factory, monkeypatch):
    job = _greenhouse_job(
        job_factory,
        title="Engineer",
        company="Acme",
        description="Build things",
        location="Remote, Brazil",
        remote_type="remote",
    )
    seen: dict[str, Any] = {}

    async def spy_ensure(  # noqa: PLR0917 - mirrors ensure_tailored_cv's positional signature
        job_details: Any, config: Any, profile: Any, cv_caller: Any
    ) -> Any:
        seen["tailoring"] = job_details
        return None

    async def spy_compose(  # noqa: PLR0913, PLR0917 - mirrors compose_answers' signature
        questions: Any,
        profile: Any,
        config: Any,
        job_details: Any,
        compose_caller: Any,
        *,
        job_cache: Any = None,
        answer_bank: Any = None,
    ) -> list[Any]:
        seen["composing"] = job_details
        return []

    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", _one_question)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller_for)
    monkeypatch.setattr(service, "ensure_tailored_cv", spy_ensure)
    monkeypatch.setattr(service, "compose_answers", spy_compose)

    await service.prepare_application(job.id, {}, {})

    assert seen["tailoring"] == {
        "id": job.id,
        "title": "Engineer",
        "company": "Acme",
        "description": "Build things",
    }
    assert seen["composing"] == {
        "id": job.id,
        "title": "Engineer",
        "company": "Acme",
        "description": "Build things",
        "location": "Remote, Brazil",
        "remote_type": "remote",
    }


@pytest.mark.parametrize(
    ("config", "expected_age"),
    [
        ({}, DEFAULTS["answer_bank_max_age_days"]),
        ({"answer_bank_max_age_days": 7}, 7),
    ],
)
async def test_the_answer_bank_age_comes_from_the_config_or_the_default(
    job_factory, monkeypatch, *, config, expected_age
):
    job = _greenhouse_job(job_factory)
    ages: list[Any] = []

    def spy_load(maximum_age_days: Any) -> dict[str, Any]:
        ages.append(maximum_age_days)
        return {}

    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", _one_question)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller_for)
    monkeypatch.setattr(service, "load_answer_bank", spy_load)

    await service.prepare_application(job.id, config, {})

    assert ages == [expected_age]


async def test_a_failed_paste_reading_is_logged_and_told_to_run_again(
    job_factory, monkeypatch, caplog
):
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    record_cv_bootstrap_decline()

    async def refuse(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        raise ExtractionError("not json")

    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller_for)
    monkeypatch.setattr(service, "extract_questions_from_page", refuse)

    with caplog.at_level(logging.WARNING):
        result = await service.prepare_application_from_paste(job.id, "page", {}, {})

    assert result.kind is SheetKind.NO_QUESTIONS
    assert result.error == (
        "The model's reading of that text could not be used — nothing is wrong with "
        "the paste. Just run it again."
    )
    assert f"paste extraction failed for job {job.id}: not json" in [
        record.getMessage() for record in caplog.records
    ]


async def test_a_paste_without_questions_asks_whether_the_whole_page_was_copied(
    job_factory, monkeypatch
):
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    record_cv_bootstrap_decline()

    async def nothing(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        return []

    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller_for)
    monkeypatch.setattr(service, "extract_questions_from_page", nothing)

    result = await service.prepare_application_from_paste(job.id, "page", {}, {})

    assert result.error == "No questions could be found in that text. Was the whole page copied?"


async def test_the_bootstrap_offer_says_exactly_this(job_factory, monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")

    result = await service.prepare_application(job.id, {}, {})

    assert result.error == (
        "You don't have a tailored-CV pool yet. I can draft one from your profile.yaml — "
        "call the bootstrap_cv_pool tool to generate it, or skip_cv_bootstrap if you'd "
        "rather not use this feature. I'll keep offering this on every "
        "prepare_application until you either bootstrap a pool or skip it. "
        "From a shell: `moonlighter-apply bootstrap-cv` (add --skip to decline)."
    )


def test_the_required_keywords_are_frozen():
    assert service._REQUIRED_KEYWORDS == {
        "LinkedIn": ("linkedin",),
        "Salary expectation": (
            "salary",
            "salário",
            "salario",
            "salarial",
            "pretensão",
            "pretensao",
            "remuneração",
            "remuneracao",
        ),
        "CV": ("cv", "currículo", "curriculo", "curriculum", "resume", "résumé"),
        "Location": ("location", "localização", "localizacao", "cidade"),
    }
