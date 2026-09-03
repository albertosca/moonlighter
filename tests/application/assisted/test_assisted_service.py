"""Tests for prepare_application / prepare_application_from_paste.

Routing is the point of this module: the wrong ATS branch producing the right
answer text is a bug that "does it return the paste hint" alone would miss.
Every routing assertion here is paired with proof that the branch NOT taken
was in fact not taken (an API not called, a fake LLM never consulted).
"""

from typing import Any

from moonlighter.application.assisted import service
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.core.db import Application


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


async def test_sheet_generates_the_tailored_cv_before_composing(job_factory, monkeypatch):
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/9")
    question = FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)
    seen = {}

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [question]

    async def spy_ensure(job_dict: Any, config: Any, profile: Any, caller: Any) -> Any:
        seen["job"] = job_dict
        return None

    monkeypatch.setattr(service, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(service, "fetch_recruitee_questions", _never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller())
    monkeypatch.setattr(service, "ensure_tailored_cv", spy_ensure)

    await service.prepare_application(job.id, {}, {})

    assert seen["job"]["id"] == job.id
    assert seen["job"]["company"] == job.company


async def test_sheet_builds_one_caller_and_reuses_it_for_both_llm_users(job_factory, monkeypatch):
    # Regression for the api-mode cost bug: _sheet used to call make_caller(config)
    # twice, instantiating a second Anthropic SDK client per sheet. One call, one
    # caller, shared by the tailored-CV step and the composer.
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/11")
    question = FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)
    calls = 0
    caller = _stub_caller()
    seen: dict[str, Any] = {}

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [question]

    def counting_make_caller(config: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AssertionError("make_caller must be called at most once per _sheet")
        return caller

    async def spy_ensure(job_dict: Any, config: Any, profile: Any, cv_caller: Any) -> Any:
        seen["cv_caller"] = cv_caller
        return None

    async def spy_compose(
        questions: Any, profile: Any, config: Any, job_dict: Any, compose_caller: Any
    ) -> list[Any]:
        seen["compose_caller"] = compose_caller
        return []

    monkeypatch.setattr(service, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(service, "fetch_recruitee_questions", _never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", counting_make_caller)
    monkeypatch.setattr(service, "ensure_tailored_cv", spy_ensure)
    monkeypatch.setattr(service, "compose_answers", spy_compose)

    await service.prepare_application(job.id, {}, {})

    assert calls == 1
    assert seen["cv_caller"] is caller
    assert seen["compose_caller"] is caller


async def test_sheet_notes_the_uncompiled_tex(job_factory, monkeypatch, tmp_path):
    from moonlighter.application.cvgen.service import TailoredCV

    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/9")
    question = FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)
    tex = tmp_path / "cv.tex"
    tex.write_text("x")

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [question]

    async def uncompiled(job_dict: Any, config: Any, profile: Any, caller: Any) -> Any:
        return TailoredCV(path=tex, compiled=False)

    monkeypatch.setattr(service, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(service, "fetch_recruitee_questions", _never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller())
    monkeypatch.setattr(service, "ensure_tailored_cv", uncompiled)

    out = await service.prepare_application(job.id, {}, {})

    assert "pdflatex" in out and "cv.tex" in out
    # The CV gap names the DEFAULT CV in the tex-only case (resolve_cv_path
    # refuses a dir with no pdf), so "compile it" without "then upload that
    # one" leaves the operator compiling a tailored CV and uploading the
    # generic one.
    assert "then upload the resulting cv.pdf instead of the CV named above" in out


async def test_a_compiled_cv_reaches_the_sheet_when_no_cv_question_exists(
    job_factory, monkeypatch, tmp_path
):
    # The compiled path otherwise surfaces only through the composer's CV FILE
    # branch, which needs a FILE question with a CV-shaped label. A paste that
    # missed the resume field produces a tailored PDF nobody is told about --
    # and the spec's "the sheet always instructs human review" is not met.
    from moonlighter.application.cvgen.service import TailoredCV

    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/9")
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF")

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)]

    async def compiled(job_dict: Any, config: Any, profile: Any, caller: Any) -> Any:
        return TailoredCV(path=pdf, compiled=True)

    monkeypatch.setattr(service, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(service, "fetch_recruitee_questions", _never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller())
    monkeypatch.setattr(service, "ensure_tailored_cv", compiled)

    out = await service.prepare_application(job.id, {}, {})

    assert str(pdf) in out
    assert "review it before uploading" in out


async def test_a_compiled_cv_already_named_by_a_cv_gap_is_not_repeated(
    job_factory, monkeypatch, tmp_path
):
    from moonlighter.application.cvgen.service import TailoredCV

    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/9")
    generated = tmp_path / "generated"
    out_dir = generated / str(job.id)
    out_dir.mkdir(parents=True)
    pdf = out_dir / "cv.pdf"
    pdf.write_bytes(b"%PDF")
    config = {"cv": {"generated_dir": str(generated)}}

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [FormQuestion(label="Resume", kind=QuestionKind.FILE, required=True)]

    async def compiled(job_dict: Any, config: Any, profile: Any, caller: Any) -> Any:
        return TailoredCV(path=pdf, compiled=True)

    monkeypatch.setattr(service, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(service, "fetch_recruitee_questions", _never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller())
    monkeypatch.setattr(service, "ensure_tailored_cv", compiled)

    out = await service.prepare_application(job.id, config, {})

    assert out.count(str(pdf)) == 1  # the CV gap already names it
    assert "Upload this CV for this job" not in out


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


# ── tracking alias ──────────────────────────────────────────────────────────
# The company replies to <account>+<ref>@domain, which is how the email monitor
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
    job = job_factory(source="lever", url="https://jobs.lever.co/x/y")
    monkeypatch.setattr(service, "extract_questions_from_page", _extract_email_and_essay)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller())

    out = await service.prepare_application_from_paste(
        job.id, "the page", _TRACKING_CONFIG, {"email": "personal@gmail.com"}
    )

    application = Application.get(Application.job == job)
    assert application.email_ref
    assert f"track+{application.email_ref}@example.com" in out
    assert "personal@gmail.com" not in out


async def test_preparing_twice_reuses_the_same_application_and_ref(job_factory, monkeypatch):
    job = job_factory(source="lever", url="https://jobs.lever.co/x/y")
    monkeypatch.setattr(service, "extract_questions_from_page", _extract_email_and_essay)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller())

    first = await service.prepare_application_from_paste(job.id, "p", _TRACKING_CONFIG, {})
    ref = Application.get(Application.job == job).email_ref
    second = await service.prepare_application_from_paste(job.id, "p", _TRACKING_CONFIG, {})

    assert Application.select().where(Application.job == job).count() == 1
    assert Application.get(Application.job == job).email_ref == ref
    assert f"+{ref}@" in first
    assert f"+{ref}@" in second


async def test_an_unanswered_email_question_is_answered_by_the_alias(job_factory, monkeypatch):
    # No profile email: field_map yields "" and the composer records a gap. The
    # alias is still the right answer — tracking must not depend on the profile
    # carrying an email address.
    job = job_factory(source="lever", url="https://jobs.lever.co/x/y")
    monkeypatch.setattr(service, "extract_questions_from_page", _extract_email_and_essay)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller())

    out = await service.prepare_application_from_paste(job.id, "p", _TRACKING_CONFIG, {})

    ref = Application.get(Application.job == job).email_ref
    assert f"track+{ref}@example.com" in out


async def test_without_email_config_the_sheet_keeps_the_profile_email(job_factory, monkeypatch):
    job = job_factory(source="lever", url="https://jobs.lever.co/x/y")
    monkeypatch.setattr(service, "extract_questions_from_page", _extract_email_and_essay)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller())

    out = await service.prepare_application_from_paste(
        job.id, "p", {}, {"email": "personal@gmail.com"}
    )

    assert "personal@gmail.com" in out
    assert Application.get_or_none(Application.job == job) is None


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

    job = job_factory(source="lever", url="https://jobs.lever.co/x/y")
    monkeypatch.setattr(service, "extract_questions_from_page", extract)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller("Yes"))

    out = await service.prepare_application_from_paste(job.id, "p", _TRACKING_CONFIG, {})

    # The choice keeps its own answer; the alias reaches the operator through
    # the footer instead, since no text question could carry it.
    ref = Application.get(Application.job == job).email_ref
    assert "> Yes" in out
    assert f"use: track+{ref}@example.com" in out


async def test_an_alias_with_no_email_question_is_surfaced_on_the_sheet(job_factory, monkeypatch):
    # A source that publishes no email question (a paste that missed it, an API
    # that omits standard fields) must still hand the operator the alias — it
    # already exists in the DB, and a sheet that hides it sends the reply to a
    # mailbox the monitor never reads. Found live on the Curotec gate leg.
    async def extract(page_text: str, llm_caller: Any) -> list[FormQuestion]:
        return [FormQuestion(label="Why us?", kind=QuestionKind.LONG_TEXT, required=True)]

    job = job_factory(source="lever", url="https://jobs.lever.co/x/y")
    monkeypatch.setattr(service, "extract_questions_from_page", extract)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller())

    out = await service.prepare_application_from_paste(job.id, "p", _TRACKING_CONFIG, {})

    ref = Application.get(Application.job == job).email_ref
    assert f"track+{ref}@example.com" in out


async def test_the_api_path_carries_the_alias_too(job_factory, monkeypatch):
    # The injection lives on the shared sheet path, but each public entry point
    # is proven separately — a fix that reconciles only one path is how the
    # last silent regression happened.
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/1")

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [FormQuestion(label="E-mail", kind=QuestionKind.TEXT, required=True)]

    monkeypatch.setattr(service, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(service, "fetch_recruitee_questions", _never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", lambda config: _stub_caller())

    out = await service.prepare_application(job.id, _TRACKING_CONFIG, {})

    ref = Application.get(Application.job == job).email_ref
    assert f"track+{ref}@example.com" in out


async def test_a_manual_job_with_a_greenhouse_url_still_gets_the_api(job_factory, monkeypatch):
    # add_job stores source='manual' even for a recognizable Greenhouse URL
    # (EU job-boards host included) — routing must key on the URL, not on how
    # the job entered the DB. Found live: Teachable, job-boards.eu, 2026-08-18.
    job = job_factory(
        source="manual",
        url="https://job-boards.eu.greenhouse.io/teachablecareers/jobs/4913809101?gh_src=x",
    )
    seen: dict[str, str] = {}

    async def fake_fetch(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        seen["board"], seen["job_id"] = board, job_id
        return [FormQuestion(label="Email", kind=QuestionKind.TEXT, required=True, options=())]

    monkeypatch.setattr(service, "fetch_greenhouse_questions", fake_fetch)
    monkeypatch.setattr(service, "fetch_recruitee_questions", _never_fetch_recruitee)

    out = await service.prepare_application(job.id, {}, {})

    assert seen == {"board": "teachablecareers", "job_id": "4913809101"}
    assert "prepare_application_from_paste" not in out
