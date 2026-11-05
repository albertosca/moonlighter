"""The rendered sheet text for every outcome, pinned byte-for-byte by snapshots."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.results import SheetKind, SheetResult, render_sheet_result
from moonlighter.application.assisted.service import (
    prepare_application,
    prepare_application_from_paste,
)
from moonlighter.application.cvgen.service import TailoredCV
from moonlighter.core.db import init_db

from tests.application.assisted.sheet_inputs import CONFIG, PAGE, PROFILE, QUESTIONS, create_job


async def test_prepare_application_plain_sheet_is_unchanged(temporary_database, snapshot_text):
    job = create_job()
    with (
        patch(
            "moonlighter.application.assisted.service._api_form",
            new=AsyncMock(return_value=(QUESTIONS, ())),
        ),
        patch(
            "moonlighter.application.assisted.service.ensure_tailored_cv",
            new=AsyncMock(return_value=None),
        ),
        patch("moonlighter.application.assisted.service._tracking_alias", return_value=None),
    ):
        out = render_sheet_result(await prepare_application(job.id, CONFIG, PROFILE))
    snapshot_text(out, "plain_sheet")


async def test_prepare_application_appends_the_alias_note(temporary_database, snapshot_text):
    # The alias note fires only when NO question on the sheet takes the alias,
    # so this passes a question list with no email field.
    job = create_job(url="https://boards.greenhouse.io/acme/jobs/2")
    no_email = [FormQuestion(label="Full name", kind=QuestionKind.TEXT, options=[], required=True)]
    with (
        patch(
            "moonlighter.application.assisted.service._api_form",
            new=AsyncMock(return_value=(no_email, ())),
        ),
        patch(
            "moonlighter.application.assisted.service.ensure_tailored_cv",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "moonlighter.application.assisted.service._tracking_alias",
            return_value="jane+ab12cd@example.com",
        ),
    ):
        result = await prepare_application(job.id, CONFIG, PROFILE)
    # .alias is the one machine-usable field on SheetResult -- render_sheet_result
    # never reads it (only .alias_note, the human-facing footer), so it can drift
    # to None with the suite still green unless something asserts it directly.
    assert result.alias == "jane+ab12cd@example.com"
    snapshot_text(render_sheet_result(result), "alias_note")


async def test_prepare_application_appends_the_uncompiled_cv_note(
    temporary_database, snapshot_text
):
    job = create_job(url="https://boards.greenhouse.io/acme/jobs/3")
    uncompiled = TailoredCV(Path("/tmp/moonlighter-test-cv/cv.tex"), compiled=False)
    with (
        patch(
            "moonlighter.application.assisted.service._api_form",
            new=AsyncMock(return_value=(QUESTIONS, ())),
        ),
        patch(
            "moonlighter.application.assisted.service.ensure_tailored_cv",
            new=AsyncMock(return_value=uncompiled),
        ),
        patch("moonlighter.application.assisted.service._tracking_alias", return_value=None),
    ):
        out = render_sheet_result(await prepare_application(job.id, CONFIG, PROFILE))
    snapshot_text(out, "cv_note")


async def test_prepare_application_appends_the_compiled_cv_note(temporary_database, snapshot_text):
    # Compiled CV, no CV/FILE question on the sheet to name it -- _names_path is
    # False since none of QUESTIONS carries a gap_reason mentioning this path.
    job = create_job(url="https://boards.greenhouse.io/acme/jobs/4")
    compiled = TailoredCV(Path("/tmp/moonlighter-test-cv/cv.pdf"), compiled=True)
    with (
        patch(
            "moonlighter.application.assisted.service._api_form",
            new=AsyncMock(return_value=(QUESTIONS, ())),
        ),
        patch(
            "moonlighter.application.assisted.service.ensure_tailored_cv",
            new=AsyncMock(return_value=compiled),
        ),
        patch("moonlighter.application.assisted.service._tracking_alias", return_value=None),
    ):
        out = render_sheet_result(await prepare_application(job.id, CONFIG, PROFILE))
    snapshot_text(out, "compiled_cv_note")


async def test_prepare_application_job_not_found_is_unchanged(temporary_database, snapshot_text):
    init_db()
    snapshot_text(
        render_sheet_result(await prepare_application(4242, CONFIG, PROFILE)), "job_not_found"
    )


async def test_prepare_application_with_no_questions_returns_the_paste_hint(
    temporary_database, snapshot_text
):
    job = create_job(url="https://boards.greenhouse.io/acme/jobs/5")
    with patch(
        "moonlighter.application.assisted.service._api_form",
        new=AsyncMock(return_value=([], ())),
    ):
        out = render_sheet_result(await prepare_application(job.id, CONFIG, PROFILE))
    snapshot_text(out, "paste_hint")


def test_render_sheet_result_reproduces_the_plain_sheet(composed_fixture, snapshot_text):
    result = SheetResult(
        kind=SheetKind.SHEET,
        composed=composed_fixture,
        job_title="Staff Engineer",
        company="Acme",
        apply_url="https://boards.greenhouse.io/acme/jobs/1",
        alias=None,
        alias_note=None,
        cv_note=None,
        error=None,
    )
    snapshot_text(render_sheet_result(result), "plain_sheet")


async def test_prepare_from_paste_sheet_is_unchanged(temporary_database, snapshot_text):
    job = create_job(url="https://boards.greenhouse.io/acme/jobs/4")
    with (
        patch(
            "moonlighter.application.assisted.service._api_form",
            new=AsyncMock(return_value=([], ())),
        ),
        patch(
            "moonlighter.application.assisted.service.extract_questions_from_page",
            new=AsyncMock(return_value=QUESTIONS),
        ),
        patch(
            "moonlighter.application.assisted.service.ensure_tailored_cv",
            new=AsyncMock(return_value=None),
        ),
        patch("moonlighter.application.assisted.service._tracking_alias", return_value=None),
    ):
        out = render_sheet_result(
            await prepare_application_from_paste(job.id, PAGE, CONFIG, profile=PROFILE)
        )
    snapshot_text(out, "paste_sheet")


async def test_prepare_from_paste_no_questions_is_unchanged(temporary_database, snapshot_text):
    job = create_job(url="https://boards.greenhouse.io/acme/jobs/5")
    with (
        patch(
            "moonlighter.application.assisted.service._api_form",
            new=AsyncMock(return_value=([], ())),
        ),
        patch(
            "moonlighter.application.assisted.service.extract_questions_from_page",
            new=AsyncMock(return_value=[]),
        ),
    ):
        out = render_sheet_result(
            await prepare_application_from_paste(job.id, PAGE, CONFIG, profile=PROFILE)
        )
    snapshot_text(out, "paste_no_questions")


async def test_prepare_from_paste_job_not_found_is_unchanged(temporary_database, snapshot_text):
    init_db()
    out = render_sheet_result(
        await prepare_application_from_paste(4242, PAGE, CONFIG, profile=PROFILE)
    )
    snapshot_text(out, "paste_job_not_found")
