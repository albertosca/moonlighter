from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from moonlighter.application.assisted.composer import ComposedAnswer
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.results import SheetKind, SheetResult, render_sheet_result
from moonlighter.application.assisted.service import (
    prepare_application,
    prepare_application_from_paste,
)
from moonlighter.application.cvgen.service import TailoredCV
from moonlighter.core.db import Job, init_db

CONFIG = {"llm_model": "claude-sonnet-4-6"}
PROFILE = {"name": "Jane Doe", "email": "jane@example.com"}
QUESTIONS = [
    FormQuestion(label="Full name", kind=QuestionKind.TEXT, options=[], required=True),
    FormQuestion(label="Email", kind=QuestionKind.TEXT, options=[], required=True),
]
PAGE = "Full name\nEmail\nWhy do you want to work here?"


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
        result = await prepare_application(job.id, CONFIG, PROFILE)
    # .alias is the one machine-usable field on SheetResult -- render_sheet_result
    # never reads it (only .alias_note, the human-facing footer), so it can drift
    # to None with the suite still green unless something asserts it directly.
    assert result.alias == "jane+ab12cd@example.com"
    snapshot_text(render_sheet_result(result), "alias_note")


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


def test_render_sheet_result_orders_alias_note_before_cv_note(composed_fixture):
    # The relative order of the two footers is part of the byte-identical MCP
    # contract -- swapping (alias_note, cv_note) to (cv_note, alias_note) in
    # render_sheet_result's loop leaves every other test green.
    result = SheetResult(
        kind=SheetKind.SHEET,
        composed=composed_fixture,
        job_title="Staff Engineer",
        company="Acme",
        apply_url="https://boards.greenhouse.io/acme/jobs/1",
        alias="jane+ab12cd@example.com",
        alias_note="Where the form asks for an email address, use: jane+ab12cd@example.com",
        cv_note="Upload this CV for this job: /tmp/cv.pdf (tailored for this job — review it before uploading)",
        error=None,
    )
    rendered = render_sheet_result(result)
    alias_at = rendered.index("Where the form asks for an email address")
    cv_at = rendered.index("Upload this CV for this job")
    assert alias_at < cv_at


async def test_prepare_from_paste_sheet_is_unchanged(tmp_db, snapshot_text):
    job = _job(tmp_db, url="https://boards.greenhouse.io/acme/jobs/4")
    with (
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
            await prepare_application_from_paste(job.id, PAGE, CONFIG, PROFILE)
        )
    snapshot_text(out, "paste_sheet")


async def test_prepare_from_paste_no_questions_is_unchanged(tmp_db, snapshot_text):
    job = _job(tmp_db, url="https://boards.greenhouse.io/acme/jobs/5")
    with patch(
        "moonlighter.application.assisted.service.extract_questions_from_page",
        new=AsyncMock(return_value=[]),
    ):
        out = render_sheet_result(
            await prepare_application_from_paste(job.id, PAGE, CONFIG, PROFILE)
        )
    snapshot_text(out, "paste_no_questions")


async def test_prepare_from_paste_job_not_found_is_unchanged(tmp_db, snapshot_text):
    init_db()
    out = render_sheet_result(await prepare_application_from_paste(4242, PAGE, CONFIG, PROFILE))
    snapshot_text(out, "paste_job_not_found")


def test_sheet_result_kind_and_error_agree():
    from moonlighter.application.assisted.results import SheetKind, SheetResult

    with pytest.raises(ValueError, match="sheet"):
        SheetResult(
            kind=SheetKind.SHEET, composed=[], job_title="", company="", apply_url="", error="x"
        )
    with pytest.raises(ValueError, match="job_not_found"):
        SheetResult(
            kind=SheetKind.JOB_NOT_FOUND, composed=[], job_title="", company="", apply_url=""
        )


async def test_prepare_application_reports_the_cv_path_and_compiled_flag(tmp_db):
    # cv_note carried the path inside an English sentence; a script needs the
    # path and the flag as fields. The note is unchanged (snapshot).
    job = _job(tmp_db, url="https://boards.greenhouse.io/acme/jobs/9")
    compiled = TailoredCV(path=Path("/tmp/cv-generated/9/cv.pdf"), compiled=True)
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
        result = await prepare_application(job.id, CONFIG, PROFILE)
    assert result.kind is SheetKind.SHEET
    assert result.cv_path == "/tmp/cv-generated/9/cv.pdf"
    assert result.cv_compiled is True


async def test_prepare_application_needs_paste_carries_the_job_url(tmp_db):
    # failed_sheet() built apply_url="" for every early-check failure, but the
    # NEEDS_PASTE call site has job.url in hand (it's already in PASTE_HINT's
    # message) -- a script reading apply_url off a needs_paste result got
    # nothing instead of the URL it needs to open and paste from.
    job = _job(tmp_db, url="https://boards.greenhouse.io/acme/jobs/6")
    with patch(
        "moonlighter.application.assisted.service._questions_from_api",
        new=AsyncMock(return_value=[]),
    ):
        result = await prepare_application(job.id, CONFIG, PROFILE)
    assert result.kind == SheetKind.NEEDS_PASTE
    assert result.apply_url == job.url


async def test_prepare_application_not_found_has_the_kind_a_script_can_switch_on(tmp_db):
    init_db()
    result = await prepare_application(4242, CONFIG, PROFILE)
    assert result.kind is SheetKind.JOB_NOT_FOUND
    assert result.error == "Job 4242 not found."


def test_sheet_result_to_dict_is_json_serialisable(composed_fixture):
    import json

    from moonlighter.application.assisted.results import (
        SheetKind,
        SheetResult,
        sheet_result_to_dict,
    )

    result = SheetResult(
        kind=SheetKind.SHEET,
        composed=composed_fixture,
        job_title="Staff Engineer",
        company="Acme",
        apply_url="https://x",
        alias="jane+ab12@x.com",
        alias_note="Where the form asks...",
        cv_path="/p/cv.pdf",
        cv_compiled=True,
    )
    d = sheet_result_to_dict(result)
    json.dumps(d)
    assert d["kind"] == "sheet"
    assert d["alias"] == "jane+ab12@x.com"
    assert d["cv"] == {"path": "/p/cv.pdf", "compiled": True}
    first = d["answers"][0]
    assert set(first) == {"label", "kind", "required", "options", "answer", "gap_reason"}
    assert d["notes"] == {"alias": "Where the form asks...", "cv": None}


def test_sheet_result_to_dict_pins_the_needs_paste_and_no_questions_wire_values():
    # A CLI consumer switches on the exact string over the wire -- pin both
    # non-SHEET kinds a script can see, not just SHEET (see sheet_result_to_dict
    # above). Renaming either StrEnum member's value left the suite green
    # before this test existed (mutation checked, reverted).
    from moonlighter.application.assisted.results import (
        SheetKind,
        SheetResult,
        sheet_result_to_dict,
    )

    needs_paste = sheet_result_to_dict(
        SheetResult(
            kind=SheetKind.NEEDS_PASTE,
            composed=[],
            job_title="",
            company="",
            apply_url="",
            error="paste it",
        )
    )
    assert needs_paste["kind"] == "needs_paste"

    no_questions = sheet_result_to_dict(
        SheetResult(
            kind=SheetKind.NO_QUESTIONS,
            composed=[],
            job_title="",
            company="",
            apply_url="",
            error="no questions",
        )
    )
    assert no_questions["kind"] == "no_questions"


def test_sheet_kind_posting_unreadable_is_pinned():
    from moonlighter.application.assisted.results import (
        SheetKind,
        SheetResult,
        sheet_result_to_dict,
    )

    r = SheetResult(
        kind=SheetKind.POSTING_UNREADABLE,
        composed=[],
        job_title="",
        company="",
        apply_url="https://x",
        error="The posting at https://x could not be read.",
    )
    assert sheet_result_to_dict(r)["kind"] == "posting_unreadable"
