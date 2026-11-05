"""How a multi-select question lists its chosen and unchosen options, including past twenty."""

from moonlighter.application.assisted.composition.composed_answer import ComposedAnswer
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sheet.builder import render_sheet

from tests.application.assisted.sheet.builder.sheet_answers import (
    HEADER,
    choice,
    entry_block,
    multi_choice,
)


def test_multi_select_renders_every_chosen_option():
    question = FormQuestion(
        label="Which of these do you know?",
        kind=QuestionKind.MULTI_SELECT,
        required=True,
        options=("Ruby", "Elixir", ".NET"),
    )
    sheet = render_sheet(
        [ComposedAnswer(question, "Ruby\nElixir", None)],
        job_title="T",
        company="C",
        apply_url="http://x",
    )
    assert "> Ruby" in sheet
    assert "> Elixir" in sheet
    assert "not chosen: .NET" in sheet
    assert "pick any of 3" in sheet


def test_multi_select_with_every_option_chosen_has_no_not_chosen_line():
    question = FormQuestion(
        label="Which of these do you know?",
        kind=QuestionKind.MULTI_SELECT,
        required=True,
        options=("Ruby", "Elixir"),
    )
    sheet = render_sheet(
        [ComposedAnswer(question, "Ruby\nElixir", None)],
        job_title="T",
        company="C",
        apply_url="http://x",
    )
    assert "not chosen" not in sheet


def _numbered_options(count: int) -> tuple[str, ...]:
    return tuple(f"Option {number}" for number in range(1, count + 1))


def test_more_than_twenty_unchosen_options_are_summarised_not_listed():
    # A Lever select with 3,301 countries made a ~108 KB sheet out of one question.
    options = _numbered_options(22)
    sheet = render_sheet([choice("Country?", options, "Option 1")], **HEADER)
    entry = entry_block(sheet, "[1/1]")
    assert "  not chosen: 21 other options (see the form)" in entry.splitlines()
    assert "Option 22" not in entry


def test_twenty_unchosen_options_are_still_listed():
    options = _numbered_options(21)
    sheet = render_sheet([choice("Country?", options, "Option 1")], **HEADER)
    entry = entry_block(sheet, "[1/1]")
    assert f"  not chosen: {' / '.join(options[1:])}" in entry.splitlines()


def test_a_multi_select_with_more_than_twenty_unchosen_options_is_summarised():
    options = _numbered_options(23)
    sheet = render_sheet([multi_choice("Languages?", options, "Option 1\nOption 2")], **HEADER)
    entry = entry_block(sheet, "[1/1]")
    assert "  not chosen: 21 other options (see the form)" in entry.splitlines()
    assert "Option 23" not in entry
