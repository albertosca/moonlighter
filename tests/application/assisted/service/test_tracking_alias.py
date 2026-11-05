"""The tracking alias: replies go to a mailbox the monitor reads, so the sheet carries the alias, not the profile email."""

from typing import Any

from moonlighter.application.assisted import service
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sheet.results import render_sheet_result
from moonlighter.application.assisted.sources import greenhouse as greenhouse_source
from moonlighter.application.assisted.sources import recruitee as recruitee_source
from moonlighter.core.db import Application
from tests.application.assisted.service.service_fakes import (
    bypass_cv_bootstrap_offer,
    never_fetch_recruitee,
    stub_caller,
)

# The company replies to <account>+<reference>@domain, which is how the email monitor
# matches the reply back to the application. The sheet must therefore carry the
# alias: the raw profile email routes replies to a mailbox the monitor never
# reads. Found live on the first gate application (2026-08-13) — the deleted
# automation was the alias code's only caller.

_TRACKING_CONFIG = {"email": {"address": "track@example.com"}}


async def _extract_email_and_essay(page_text: str, llm_caller: Any) -> list[FormQuestion]:
    return [
        FormQuestion(label="Email", kind=QuestionKind.TEXT, required=True),
        FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True),
    ]


async def test_the_email_answer_carries_the_tracking_alias_not_the_profile_email(
    job_factory, monkeypatch
):
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(service, "extract_questions_from_page", _extract_email_and_essay)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())

    out = render_sheet_result(
        await service.prepare_application_from_paste(
            job.id, "the page", _TRACKING_CONFIG, profile={"email": "personal@gmail.com"}
        )
    )

    application = Application.get(Application.job == job)
    assert application.email_ref
    assert f"track+{application.email_ref}@example.com" in out
    assert "personal@gmail.com" not in out


async def test_preparing_twice_reuses_the_same_application_and_ref(job_factory, monkeypatch):
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(service, "extract_questions_from_page", _extract_email_and_essay)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())

    first = render_sheet_result(
        await service.prepare_application_from_paste(job.id, "p", _TRACKING_CONFIG, profile={})
    )
    reference = Application.get(Application.job == job).email_ref
    second = render_sheet_result(
        await service.prepare_application_from_paste(job.id, "p", _TRACKING_CONFIG, profile={})
    )

    assert Application.select().where(Application.job == job).count() == 1
    assert Application.get(Application.job == job).email_ref == reference
    assert f"+{reference}@" in first
    assert f"+{reference}@" in second


async def test_an_unanswered_email_question_is_answered_by_the_alias(job_factory, monkeypatch):
    # No profile email: field_map yields "" and the composer records a gap. The
    # alias is still the right answer — tracking must not depend on the profile
    # carrying an email address.
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(service, "extract_questions_from_page", _extract_email_and_essay)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())

    out = render_sheet_result(
        await service.prepare_application_from_paste(job.id, "p", _TRACKING_CONFIG, profile={})
    )

    reference = Application.get(Application.job == job).email_ref
    assert f"track+{reference}@example.com" in out


async def test_without_email_config_the_sheet_keeps_the_profile_email(job_factory, monkeypatch):
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(service, "extract_questions_from_page", _extract_email_and_essay)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())

    out = render_sheet_result(
        await service.prepare_application_from_paste(
            job.id, "p", {}, profile={"email": "personal@gmail.com"}
        )
    )

    assert "personal@gmail.com" in out
    # _sheet now always ensures an Application row exists (Layer A's per-job answer
    # cache needs one regardless of email tracking) — but with no email config, no
    # alias is minted, so email_ref stays unset.
    assert Application.get(Application.job == job).email_ref is None


async def test_a_choice_question_mentioning_email_is_not_overwritten(job_factory, monkeypatch):
    async def extract(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        return [
            FormQuestion(
                label="Email updates",
                kind=QuestionKind.SINGLE_SELECT,
                required=False,
                options=("Yes", "No"),
            )
        ]

    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(service, "extract_questions_from_page", extract)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller("Yes"))

    out = render_sheet_result(
        await service.prepare_application_from_paste(job.id, "p", _TRACKING_CONFIG, profile={})
    )

    # The choice keeps its own answer; the alias reaches the operator through
    # the footer instead, since no text question could carry it.
    reference = Application.get(Application.job == job).email_ref
    assert "> Yes" in out
    assert f"use: track+{reference}@example.com" in out


async def test_an_alias_with_no_email_question_is_surfaced_on_the_sheet(job_factory, monkeypatch):
    # A source that publishes no email question (a paste that missed it, an API
    # that omits standard fields) must still hand the operator the alias — it
    # already exists in the DB, and a sheet that hides it sends the reply to a
    # mailbox the monitor never reads. Found live on the Curotec gate leg.
    async def extract(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        return [FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)]

    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    bypass_cv_bootstrap_offer()
    monkeypatch.setattr(service, "extract_questions_from_page", extract)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())

    out = render_sheet_result(
        await service.prepare_application_from_paste(job.id, "p", _TRACKING_CONFIG, profile={})
    )

    reference = Application.get(Application.job == job).email_ref
    assert f"track+{reference}@example.com" in out


async def test_the_api_path_carries_the_alias_too(job_factory, monkeypatch):
    # The injection lives on the shared sheet path, but each public entry point
    # is proven separately — a fix that reconciles only one path is how the
    # last silent regression happened.
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/1")
    bypass_cv_bootstrap_offer()

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [FormQuestion(label="E-mail", kind=QuestionKind.TEXT, required=True)]

    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())

    out = render_sheet_result(await service.prepare_application(job.id, _TRACKING_CONFIG, {}))

    reference = Application.get(Application.job == job).email_ref
    assert f"track+{reference}@example.com" in out


async def test_a_manual_job_with_a_greenhouse_url_still_gets_the_api(job_factory, monkeypatch):
    # add_job stores source='manual' even for a recognizable Greenhouse URL
    # (EU job-boards host included) — routing must key on the URL, not on how
    # the job entered the DB. Found live: Teachable, job-boards.eu, 2026-08-18.
    job = job_factory(
        source="manual",
        url="https://job-boards.eu.greenhouse.io/teachablecareers/jobs/4913809101?gh_src=x",
    )
    bypass_cv_bootstrap_offer()
    seen: dict[str, str] = {}

    async def fake_fetch(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        seen["board"], seen["job_id"] = board, job_id
        return [FormQuestion(label="Email", kind=QuestionKind.TEXT, required=True, options=())]

    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", fake_fetch)
    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", never_fetch_recruitee)

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert seen == {"board": "teachablecareers", "job_id": "4913809101"}
    assert "prepare_application_from_paste" not in out
