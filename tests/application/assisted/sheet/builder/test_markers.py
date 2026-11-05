"""The per-question markers of a rendered sheet: numbering, required, gap and pick-one or pick-any."""

from moonlighter.application.assisted.sheet.builder import render_sheet

from tests.application.assisted.sheet.builder.sheet_answers import (
    HEADER,
    answered,
    choice,
    entry_block,
    gap,
    multi_choice,
)


def test_every_question_is_numbered_out_of_the_total():
    sheet = render_sheet([answered("First Name", "Alberto"), gap("Salary", "no basis")], **HEADER)
    # Pin the number to the RIGHT question, not just present anywhere in the sheet.
    first = entry_block(sheet, "[1/2]")
    second = entry_block(sheet, "[2/2]")
    assert "First Name" in first.splitlines()[0]
    assert "Salary" in second.splitlines()[0]


def test_a_required_question_is_marked():
    sheet = render_sheet(
        [
            answered("First Name", "Alberto", required=True),
            answered("Headline", "x", required=False),
        ],
        **HEADER,
    )
    first = entry_block(sheet, "[1/2]")
    second = entry_block(sheet, "[2/2]")
    assert "(required)" in first.splitlines()[0]
    assert "(required)" not in second.splitlines()[0]


def test_an_optional_question_is_not_marked_required():
    sheet = render_sheet([answered("Headline", "x", required=False)], **HEADER)
    assert "(required)" not in sheet
    # The header line itself must not carry any parenthetical mark for an optional field.
    entry = entry_block(sheet, "[1/1]")
    assert entry.splitlines()[0] == "[1/1] Headline"


def test_a_gap_is_shouted_with_its_reason_attached_to_its_own_question():
    sheet = render_sheet(
        [answered("First Name", "Alberto"), gap("Salary", "no basis in your profile to answer")],
        **HEADER,
    )
    salary_entry = entry_block(sheet, "[2/2] Salary")
    assert "!! I DON'T KNOW" in salary_entry
    assert "no basis in your profile to answer" in salary_entry
    # The answered question must not itself be flagged as a gap.
    name_entry = entry_block(sheet, "[1/2] First Name")
    assert "!! I DON'T KNOW" not in name_entry


def test_a_choice_shows_the_pick_distinguished_from_the_alternatives():
    sheet = render_sheet([choice("Sponsorship?", ("No", "Yes, now"), "Yes, now")], **HEADER)
    entry = entry_block(sheet, "[1/1]")
    lines = entry.splitlines()
    assert "> Yes, now" in lines
    # "No" (the alternative) must appear in the "not chosen" line, never as the chosen pick
    # — regression guard for the old "options:" label, which read as if "No" were the answer.
    assert "> No" not in lines
    assert any(line.startswith("  not chosen:") and "No" in line for line in lines)


def test_a_choice_with_no_remaining_alternative_omits_the_not_chosen_line():
    sheet = render_sheet([choice("Confirm?", ("Yes",), "Yes")], **HEADER)
    entry = entry_block(sheet, "[1/1]")
    lines = entry.splitlines()
    assert "> Yes" in lines
    assert not any(line.startswith("  not chosen:") for line in lines)


def test_a_single_select_question_is_marked_pick_one_of_n():
    sheet = render_sheet([choice("Sponsorship?", ("No", "Yes, now", "Later"), "No")], **HEADER)
    entry = entry_block(sheet, "[1/1]")
    assert "pick 1 of 3" in entry.splitlines()[0]


def test_a_multi_select_question_is_marked_pick_any_of_n_not_pick_one():
    sheet = render_sheet(
        [multi_choice("Which languages?", ("Python", "Ruby", "Elixir"), "Python")], **HEADER
    )
    entry = entry_block(sheet, "[1/1]")
    header_line = entry.splitlines()[0]
    assert "pick any of 3" in header_line
    assert "pick 1 of" not in header_line
