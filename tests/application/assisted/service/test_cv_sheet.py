"""The tailored CV on the sheet: generated before composing, noted when uncompiled, never repeated."""

from typing import Any

from moonlighter.application.assisted import service
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.results import render_sheet_result
from moonlighter.application.assisted.sources import greenhouse as greenhouse_source
from moonlighter.application.assisted.sources import recruitee as recruitee_source
from moonlighter.application.cvgen.service import TailoredCV

from tests.application.assisted.service.service_fakes import (
    bypass_cv_bootstrap_offer,
    never_fetch_recruitee,
    stub_caller,
)


async def test_sheet_generates_the_tailored_cv_before_composing(job_factory, monkeypatch):
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/9")
    bypass_cv_bootstrap_offer()
    question = FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)
    seen = {}

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [question]

    async def spy_ensure(  # noqa: PLR0917 - mirrors ensure_tailored_cv's positional signature
        job_details: Any, config: Any, profile: Any, caller: Any
    ) -> Any:
        seen["job"] = job_details
        return None

    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())
    monkeypatch.setattr(service, "ensure_tailored_cv", spy_ensure)

    await service.prepare_application(job.id, {}, {})

    assert seen["job"]["id"] == job.id
    assert seen["job"]["company"] == job.company


async def test_sheet_builds_one_caller_and_reuses_it_for_both_llm_users(job_factory, monkeypatch):
    # Regression for the api-mode cost bug: _sheet used to call make_caller(config)
    # twice, instantiating a second Anthropic SDK client per sheet. One call, one
    # caller, shared by the tailored-CV step and the composer.
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/11")
    bypass_cv_bootstrap_offer()
    question = FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)
    calls = 0
    caller = stub_caller()
    seen: dict[str, Any] = {}

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [question]

    def counting_make_caller(config: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AssertionError("make_caller must be called at most once per _sheet")
        return caller

    async def spy_ensure(  # noqa: PLR0917 - mirrors ensure_tailored_cv's positional signature
        job_details: Any, config: Any, profile: Any, cv_caller: Any
    ) -> Any:
        seen["cv_caller"] = cv_caller
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
        seen["compose_caller"] = compose_caller
        return []

    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", counting_make_caller)
    monkeypatch.setattr(service, "ensure_tailored_cv", spy_ensure)
    monkeypatch.setattr(service, "compose_answers", spy_compose)

    await service.prepare_application(job.id, {}, {})

    assert calls == 1
    assert seen["cv_caller"] is caller
    assert seen["compose_caller"] is caller


async def test_sheet_notes_the_uncompiled_tex(job_factory, monkeypatch, tmp_path):
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/9")
    bypass_cv_bootstrap_offer()
    question = FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)
    tex = tmp_path / "cv.tex"
    tex.write_text("x")

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [question]

    async def uncompiled(  # noqa: PLR0917 - mirrors ensure_tailored_cv's positional signature
        job_details: Any, config: Any, profile: Any, caller: Any
    ) -> Any:
        return TailoredCV(path=tex, compiled=False)

    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())
    monkeypatch.setattr(service, "ensure_tailored_cv", uncompiled)

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert "pdflatex" in out
    assert "cv.tex" in out
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
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/9")
    bypass_cv_bootstrap_offer()
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF")

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [FormQuestion(label="Favorite language", kind=QuestionKind.TEXT, required=False)]

    async def compiled(  # noqa: PLR0917 - mirrors ensure_tailored_cv's positional signature
        job_details: Any, config: Any, profile: Any, caller: Any
    ) -> Any:
        return TailoredCV(path=pdf, compiled=True)

    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())
    monkeypatch.setattr(service, "ensure_tailored_cv", compiled)

    out = render_sheet_result(await service.prepare_application(job.id, {}, {}))

    assert str(pdf) in out
    assert "review it before uploading" in out


async def test_a_compiled_cv_already_named_by_a_cv_gap_is_not_repeated(
    job_factory, monkeypatch, tmp_path
):
    job = job_factory(source="greenhouse", url="https://job-boards.greenhouse.io/gitlab/jobs/9")
    bypass_cv_bootstrap_offer()
    generated = tmp_path / "generated"
    output_directory = generated / str(job.id)
    output_directory.mkdir(parents=True)
    pdf = output_directory / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.5\n...\n%%EOF\n")  # real-shaped: resolve_cv_path sniffs it
    config = {"cv": {"generated_dir": str(generated)}}

    async def one_question(board: str, job_id: str, client: Any) -> list[FormQuestion]:
        return [FormQuestion(label="Resume", kind=QuestionKind.FILE, required=True)]

    async def compiled(  # noqa: PLR0917 - mirrors ensure_tailored_cv's positional signature
        job_details: Any, config: Any, profile: Any, caller: Any
    ) -> Any:
        return TailoredCV(path=pdf, compiled=True)

    monkeypatch.setattr(greenhouse_source, "fetch_greenhouse_questions", one_question)
    monkeypatch.setattr(recruitee_source, "fetch_recruitee_questions", never_fetch_recruitee)
    monkeypatch.setattr(service, "make_caller", lambda config: stub_caller())
    monkeypatch.setattr(service, "ensure_tailored_cv", compiled)

    out = render_sheet_result(await service.prepare_application(job.id, config, {}))

    assert out.count(str(pdf)) == 1  # the CV gap already names it
    assert "Upload this CV for this job" not in out
