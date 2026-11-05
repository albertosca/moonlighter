"""Pins for what the assisted service hands to its collaborators: the ATS client, the job fields and the config."""

from typing import Any

import httpx
import pytest
from moonlighter.application.assisted import service
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sources import greenhouse as greenhouse_source
from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.db import record_cv_bootstrap_decline

from tests.application.assisted.service.service_fakes import stub_caller

GREENHOUSE_URL = "https://job-boards.greenhouse.io/acme/jobs/1"
QUESTION = FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)


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

    async def spy_ensure(job_details: Any, config: Any, profile: Any, *, caller: Any) -> Any:
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
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())
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
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())
    monkeypatch.setattr(service, "load_answer_bank", spy_load)

    await service.prepare_application(job.id, config, {})

    assert ages == [expected_age]
