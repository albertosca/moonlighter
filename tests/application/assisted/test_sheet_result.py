from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from moonlighter.application.assisted.composer import ComposedAnswer
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.results import SheetResult, render_sheet_result
from moonlighter.application.assisted.service import prepare_application
from moonlighter.application.cvgen.service import TailoredCV
from moonlighter.core.db import Job, init_db

CONFIG = {"llm_model": "claude-sonnet-4-6"}
PROFILE = {"name": "Jane Doe", "email": "jane@example.com"}
QUESTIONS = [
    FormQuestion(label="Full name", kind=QuestionKind.TEXT, options=[], required=True),
    FormQuestion(label="Email", kind=QuestionKind.TEXT, options=[], required=True),
]


def _job(tmp_db, **kwargs):
    init_db()
    defaults = {
        "source": "greenhouse",
        "company": "Acme",
        "title": "Staff Engineer",
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "score": 9.0,
        "status": "new",
    }
    defaults.update(kwargs)
    return Job.create(**defaults)


async def test_prepare_application_plain_sheet_is_unchanged(tmp_db, snapshot_text):
    job = _job(tmp_db)
    with (
        patch(
            "moonlighter.application.assisted.service._questions_from_api",
            new=AsyncMock(return_value=QUESTIONS),
        ),
        patch(
            "moonlighter.application.assisted.service.ensure_tailored_cv",
            new=AsyncMock(return_value=None),
        ),
        patch("moonlighter.application.assisted.service._tracking_alias", return_value=None),
    ):
        out = render_sheet_result(await prepare_application(job.id, CONFIG, PROFILE))
    snapshot_text(out, "plain_sheet")


async def test_prepare_application_appends_the_alias_note(tmp_db, snapshot_text):
    # The alias note fires only when NO question on the sheet takes the alias,
    # so this passes a question list with no email field.
    job = _job(tmp_db, url="https://boards.greenhouse.io/acme/jobs/2")
    no_email = [FormQuestion(label="Full name", kind=QuestionKind.TEXT, options=[], required=True)]
    with (
        patch(
            "moonlighter.application.assisted.service._questions_from_api",
            new=AsyncMock(return_value=no_email),
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
        out = render_sheet_result(await prepare_application(job.id, CONFIG, PROFILE))
    snapshot_text(out, "alias_note")


async def test_prepare_application_appends_the_uncompiled_cv_note(tmp_db, snapshot_text):
    job = _job(tmp_db, url="https://boards.greenhouse.io/acme/jobs/3")
    uncompiled = TailoredCV(Path("/tmp/moonlighter-test-cv/cv.tex"), False)
    with (
        patch(
            "moonlighter.application.assisted.service._questions_from_api",
            new=AsyncMock(return_value=QUESTIONS),
        ),
        patch(
            "moonlighter.application.assisted.service.ensure_tailored_cv",
            new=AsyncMock(return_value=uncompiled),
        ),
        patch("moonlighter.application.assisted.service._tracking_alias", return_value=None),
    ):
        out = render_sheet_result(await prepare_application(job.id, CONFIG, PROFILE))
    snapshot_text(out, "cv_note")


async def test_prepare_application_appends_the_compiled_cv_note(tmp_db, snapshot_text):
    # Compiled CV, no CV/FILE question on the sheet to name it -- _names_path is
    # False since none of QUESTIONS carries a gap_reason mentioning this path.
    job = _job(tmp_db, url="https://boards.greenhouse.io/acme/jobs/4")
    compiled = TailoredCV(Path("/tmp/moonlighter-test-cv/cv.pdf"), True)
    with (
        patch(
            "moonlighter.application.assisted.service._questions_from_api",
            new=AsyncMock(return_value=QUESTIONS),
        ),
        patch(
            "moonlighter.application.assisted.service.ensure_tailored_cv",
            new=AsyncMock(return_value=compiled),
        ),
        patch("moonlighter.application.assisted.service._tracking_alias", return_value=None),
    ):
        out = render_sheet_result(await prepare_application(job.id, CONFIG, PROFILE))
    snapshot_text(out, "compiled_cv_note")


async def test_prepare_application_job_not_found_is_unchanged(tmp_db, snapshot_text):
    init_db()
    snapshot_text(
        render_sheet_result(await prepare_application(4242, CONFIG, PROFILE)), "job_not_found"
    )


async def test_prepare_application_with_no_questions_returns_the_paste_hint(tmp_db, snapshot_text):
    job = _job(tmp_db, url="https://boards.greenhouse.io/acme/jobs/5")
    with patch(
        "moonlighter.application.assisted.service._questions_from_api",
        new=AsyncMock(return_value=[]),
    ):
        out = render_sheet_result(await prepare_application(job.id, CONFIG, PROFILE))
    snapshot_text(out, "paste_hint")


@pytest.fixture
def composed_fixture():
    return [
        ComposedAnswer(
            FormQuestion(label="Full name", kind=QuestionKind.TEXT, options=[], required=True),
            "Jane Doe",
            None,
        ),
        ComposedAnswer(
            FormQuestion(label="Email", kind=QuestionKind.TEXT, options=[], required=True),
            "jane@example.com",
            None,
        ),
    ]


def test_render_sheet_result_reproduces_the_plain_sheet(composed_fixture, snapshot_text):
    result = SheetResult(
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
