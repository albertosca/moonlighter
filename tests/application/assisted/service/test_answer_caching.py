"""Answer caching: the per-job cache, the cross-job answer bank, legacy rows and the bank's age limit."""

import json
from datetime import datetime, timedelta
from typing import Any

from moonlighter.application.answers.bank.store import promote_application
from moonlighter.application.assisted import service
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sheet.results import render_sheet_result
from moonlighter.core.db import AnswerBankEntry, Application

from tests.application.assisted.service.service_fakes import (
    bypass_cv_bootstrap_offer,
    stub_caller,
)


async def test_preparing_the_same_job_twice_reuses_the_job_cache_and_skips_the_llm(
    job_factory, monkeypatch
):
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/x/y")
    bypass_cv_bootstrap_offer()
    calls = 0

    async def one_essay(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        return [FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)]

    async def counting_caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        nonlocal calls
        calls += 1
        return "a generated answer"

    monkeypatch.setattr(service, "extract_questions_from_page", one_essay)
    monkeypatch.setattr(service, "make_caller", lambda config: counting_caller)

    await service.prepare_application_from_paste(job.id, "p", {}, profile={})
    calls_after_first = calls
    assert calls_after_first > 0

    await service.prepare_application_from_paste(job.id, "p", {}, profile={})
    assert calls == calls_after_first  # second call served entirely from the job cache


async def test_a_submitted_bank_eligible_answer_is_available_to_a_different_job(
    job_factory, monkeypatch
):
    job1 = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/acme/1")
    job2 = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/other/2")
    bypass_cv_bootstrap_offer()
    # NOT "Are you authorized to work in..." (the brief's literal example): that
    # label matches work_auth's _AUTHORIZED_RE unconditionally, so with no
    # work_authorization config it is intercepted by pre_populate_answers
    # (known) as NEEDS_REVIEW_SENTINEL *before* compose_answers ever reaches
    # the job_cache/answer_bank branch (the composer checks `known` first, by
    # design — see test_a_known_field_is_never_overridden_by_the_job_cache_or_
    # answer_bank in composer/test_job_cache.py). With that label, job1's LLM is never
    # called, job_cache stays empty, and there is nothing to promote — this
    # test would fail regardless of how _sheet wires the caches. Verified
    # empirically (uv run python -c compose_answers(...)) before swapping to a
    # label with no deterministic rule.
    label = "Do you have experience with Kubernetes in production?"

    async def one_boolean(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        return [FormQuestion(label=label, kind=QuestionKind.BOOLEAN, required=True)]

    monkeypatch.setattr(service, "extract_questions_from_page", one_boolean)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller("Yes"))

    await service.prepare_application_from_paste(job1.id, "p", {}, profile={})
    application1 = Application.get(Application.job == job1)
    # Promotion is server.py's job: simulate it here directly against the answer bank,
    # so this test does not depend on the server.
    promote_application(application1.get_form_data(), job1.id)

    # A caller that always returns "Yes" (like the one above) cannot distinguish
    # "answered from the bank" from "answered by a redundant, coincidentally
    # identical LLM call" — swap to one that raises if invoked at all, so this
    # assertion only passes when job2's answer genuinely came from answer_bank.
    async def _never_llm_here(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        raise AssertionError("the LLM must not be consulted — this answer must come from the bank")

    monkeypatch.setattr(service, "make_caller", lambda config: _never_llm_here)

    out2 = render_sheet_result(
        await service.prepare_application_from_paste(job2.id, "p", {}, profile={})
    )
    assert label in out2
    assert "Yes" in out2


async def test_a_legacy_flat_form_data_row_self_heals_into_the_new_shape(job_factory, monkeypatch):
    # 8 rows in the live DB still hold the removed browser-automation tool's flat
    # label->string form_data. compose_answers now ignores those on read instead
    # of raising TypeError, but ignoring is not enough: left in place they would
    # be re-read (and re-ignored) forever. _sheet drops anything not shaped like
    # {"answer": str, "kind": str} before persisting, so the row heals on the
    # first successful run.
    legacy_label = "Full name\xa0*"
    job = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/legacy/1")
    bypass_cv_bootstrap_offer()
    application = Application.create(
        job=job,
        status="draft",
        form_data=json.dumps({legacy_label: "Alberto Albuquerque"}),
    )

    async def one_question(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        return [FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)]

    monkeypatch.setattr(service, "extract_questions_from_page", one_question)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())

    out = render_sheet_result(
        await service.prepare_application_from_paste(job.id, "p", {}, profile={})
    )

    assert "a generated answer" in out  # the run completed instead of raising
    healed = Application.get(Application.id == application.id).get_form_data()
    assert legacy_label not in healed
    assert healed == {"Why us?": {"answer": "a generated answer", "kind": "long_text"}}


async def test_a_banked_answer_older_than_max_age_is_not_replayed(job_factory, monkeypatch):
    # Sibling of the replay test above with one difference: after promotion the
    # bank row is backdated past answer_bank_max_age_days (default 90). The
    # second job must then go to the LLM again — proven by a caller that
    # answers "No" where the banked answer said "Yes".
    job1 = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/acme/1")
    job2 = job_factory(source="smartrecruiters", url="https://jobs.smartrecruiters.com/other/2")
    bypass_cv_bootstrap_offer()
    label = "Do you have experience with Kubernetes in production?"

    async def one_boolean(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        return [FormQuestion(label=label, kind=QuestionKind.BOOLEAN, required=True)]

    monkeypatch.setattr(service, "extract_questions_from_page", one_boolean)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller("Yes"))
    await service.prepare_application_from_paste(job1.id, "p", {}, profile={})
    promote_application(Application.get(Application.job == job1).get_form_data(), job1.id)
    AnswerBankEntry.update(
        updated_at=datetime.now() - timedelta(days=100)  # noqa: DTZ005 - the database stores naive local time
    ).execute()

    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller("No"))
    out2 = render_sheet_result(
        await service.prepare_application_from_paste(job2.id, "p", {}, profile={})
    )
    assert label in out2
    assert "No" in out2
    assert "Yes" not in out2  # the stale banked answer must not leak through
