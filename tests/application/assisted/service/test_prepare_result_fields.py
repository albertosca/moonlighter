"""The structured fields a prepared application reports beside its rendered sheet."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from moonlighter.application.assisted.service import (
    prepare_application,
)
from moonlighter.application.assisted.sheet.results import SheetKind
from moonlighter.application.cvgen.latex.page_fit import TailoredCV
from moonlighter.core.db import init_db

from tests.application.assisted.sheet_inputs import CONFIG, PROFILE, QUESTIONS, create_job


async def test_prepare_application_reports_the_cv_path_and_compiled_flag(temporary_database):
    # cv_note carried the path inside an English sentence; a script needs the
    # path and the flag as fields. The note is unchanged (snapshot).
    job = create_job(url="https://boards.greenhouse.io/acme/jobs/9")
    compiled = TailoredCV(path=Path("/tmp/cv-generated/9/cv.pdf"), compiled=True)
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
        result = await prepare_application(job.id, CONFIG, PROFILE)
    assert result.kind is SheetKind.SHEET
    assert result.cv_path == "/tmp/cv-generated/9/cv.pdf"
    assert result.cv_compiled is True


async def test_prepare_application_needs_paste_carries_the_job_url(temporary_database):
    # failed_sheet() built apply_url="" for every early-check failure, but the
    # NEEDS_PASTE call site has job.url in hand (it's already in PASTE_HINT's
    # message) -- a script reading apply_url off a needs_paste result got
    # nothing instead of the URL it needs to open and paste from.
    job = create_job(url="https://boards.greenhouse.io/acme/jobs/6")
    with patch(
        "moonlighter.application.assisted.service._api_form",
        new=AsyncMock(return_value=([], ())),
    ):
        result = await prepare_application(job.id, CONFIG, PROFILE)
    assert result.kind == SheetKind.NEEDS_PASTE
    assert result.apply_url == job.url


async def test_prepare_application_not_found_has_the_kind_a_script_can_switch_on(
    temporary_database,
):
    init_db()
    result = await prepare_application(4242, CONFIG, PROFILE)
    assert result.kind is SheetKind.JOB_NOT_FOUND
    assert result.error == "Job 4242 not found."
