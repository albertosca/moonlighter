"""The sheet's header, its gap summary and what an empty or mixed sheet says."""

from moonlighter.application.assisted.sheet.builder import render_sheet
from tests.application.assisted.sheet.builder.sheet_answers import (
    HEADER,
    answered,
    choice,
    entry_block,
    gap,
)


def test_the_header_carries_the_job_and_the_apply_url():
    sheet = render_sheet([answered("First Name", "Alberto")], **HEADER)
    lines = sheet.splitlines()
    assert lines[0] == "Staff Engineer — acme"
    assert lines[1] == "https://x/apply"


def test_the_gap_count_is_summarised_so_it_cannot_be_missed():
    sheet = render_sheet([answered("A", "x"), gap("B", "r"), gap("C", "r")], **HEADER)
    assert "2 of 3" in sheet


def test_a_sheet_with_no_gaps_says_so():
    sheet = render_sheet([answered("A", "x")], **HEADER)
    assert "nothing left for you" in sheet
    assert "0 of" not in sheet


def test_an_empty_sheet_demands_a_manual_check_instead_of_claiming_success():
    sheet = render_sheet([], **HEADER)
    # Must NOT read as a completed application — the exact failure mode this sheet
    # exists to prevent (the old automation silently submitted empty sections).
    assert "nothing left for you" not in sheet
    assert "answered" not in sheet
    assert "NO QUESTIONS FOUND" in sheet
    assert "check" in sheet.lower()
    # The header (job/company/URL) still carries through so the human knows which
    # application to go check.
    assert "Staff Engineer" in sheet
    assert "https://x/apply" in sheet


def test_a_realistic_mix_keeps_every_marker_on_its_own_question():
    composed = [
        answered("First Name", "Alberto"),
        answered("Headline", "Staff Engineer", required=False),
        choice("Work authorization?", ("Yes", "No"), "Yes"),
        gap("Expected salary", "no basis in your profile to answer"),
    ]
    sheet = render_sheet(composed, **HEADER)

    name = entry_block(sheet, "[1/4] First Name")
    headline = entry_block(sheet, "[2/4] Headline")
    auth = entry_block(sheet, "[3/4] Work authorization?")
    salary = entry_block(sheet, "[4/4] Expected salary")

    assert "(required)" in name.splitlines()[0]
    assert "(required)" not in headline.splitlines()[0]
    assert "> Yes" in auth.splitlines()
    assert "not chosen: No" in auth
    assert "!! I DON'T KNOW" in salary
    assert "no basis in your profile to answer" in salary
    assert "1 of 4 need you" in sheet
