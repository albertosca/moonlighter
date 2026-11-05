"""The SheetResult contract: footer order, kind and error agreement, wire values and JSON shape."""

import json

import pytest
from moonlighter.application.assisted.sheet.results import (
    SheetKind,
    SheetResult,
    render_sheet_result,
    sheet_result_to_dict,
)


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


def test_sheet_result_kind_and_error_agree():
    with pytest.raises(ValueError, match="sheet"):
        SheetResult(
            kind=SheetKind.SHEET, composed=[], job_title="", company="", apply_url="", error="x"
        )
    with pytest.raises(ValueError, match="job_not_found"):
        SheetResult(
            kind=SheetKind.JOB_NOT_FOUND, composed=[], job_title="", company="", apply_url=""
        )


def test_sheet_result_to_dict_is_json_serialisable(composed_fixture):
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
    result_payload = sheet_result_to_dict(result)
    json.dumps(result_payload)
    assert result_payload["kind"] == "sheet"
    assert result_payload["alias"] == "jane+ab12@x.com"
    assert result_payload["cv"] == {"path": "/p/cv.pdf", "compiled": True}
    first = result_payload["answers"][0]
    assert set(first) == {"label", "kind", "required", "options", "answer", "gap_reason"}
    assert result_payload["notes"] == {
        "alias": "Where the form asks...",
        "cv": None,
        "source": None,
    }


def test_the_source_note_is_rendered_and_serialised():
    result = SheetResult(
        kind=SheetKind.SHEET,
        composed=[],
        job_title="Engineer",
        company="Acme",
        apply_url="https://x",
        source_note=(
            "The pasted text was not used: this job's ATS publishes its form,"
            " which is more reliable."
        ),
    )
    assert "The pasted text was not used" in render_sheet_result(result)
    assert sheet_result_to_dict(result)["notes"]["source"].startswith(
        "The pasted text was not used"
    )


def test_sheet_result_to_dict_pins_the_needs_paste_and_no_questions_wire_values():
    # A CLI consumer switches on the exact string over the wire -- pin both
    # non-SHEET kinds a script can see, not just SHEET (see sheet_result_to_dict
    # above). Renaming either StrEnum member's value left the suite green
    # before this test existed (mutation checked, reverted).
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
    result = SheetResult(
        kind=SheetKind.POSTING_UNREADABLE,
        composed=[],
        job_title="",
        company="",
        apply_url="https://x",
        error="The posting at https://x could not be read.",
    )
    assert sheet_result_to_dict(result)["kind"] == "posting_unreadable"


def test_cv_bootstrap_offer_is_a_valid_sheet_kind():
    assert SheetKind.CV_BOOTSTRAP_OFFER.value == "cv_bootstrap_offer"
