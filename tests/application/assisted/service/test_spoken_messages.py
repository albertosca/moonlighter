"""Pins for the words the assisted service says: the paste failures, the bootstrap offer and the required keywords."""

import logging
from typing import Any

from moonlighter.application.assisted import service
from moonlighter.application.assisted.questions import FormQuestion
from moonlighter.application.assisted.required_labels import REQUIRED_KEYWORDS
from moonlighter.application.assisted.results import SheetKind
from moonlighter.application.assisted.sources.pasted import ExtractionError
from moonlighter.core.db import record_cv_bootstrap_decline

from tests.application.assisted.service.service_fakes import stub_caller


async def test_a_failed_paste_reading_is_logged_and_told_to_run_again(
    job_factory, monkeypatch, caplog
):
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    record_cv_bootstrap_decline()

    async def refuse(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        raise ExtractionError("not json")

    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())
    monkeypatch.setattr(service, "extract_questions_from_page", refuse)

    with caplog.at_level(logging.WARNING):
        result = await service.prepare_application_from_paste(job.id, "page", {}, profile={})

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

    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())
    monkeypatch.setattr(service, "extract_questions_from_page", nothing)

    result = await service.prepare_application_from_paste(job.id, "page", {}, profile={})

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
    assert REQUIRED_KEYWORDS == {
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
