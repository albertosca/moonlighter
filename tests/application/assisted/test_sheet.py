from moonlighter.application.assisted.composer import ComposedAnswer
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind
from moonlighter.application.assisted.sheet import render_sheet

HEADER = {"job_title": "Staff Engineer", "company": "acme", "apply_url": "https://x/apply"}


def answered(label: str, answer: str, required: bool = True) -> ComposedAnswer:
    return ComposedAnswer(
        FormQuestion(label=label, kind=QuestionKind.TEXT, required=required), answer, None
    )


def gap(label: str, reason: str) -> ComposedAnswer:
    return ComposedAnswer(
        FormQuestion(label=label, kind=QuestionKind.TEXT, required=True), None, reason
    )


def choice(
    label: str, options: tuple[str, ...], picked: str, required: bool = True
) -> ComposedAnswer:
    return ComposedAnswer(
        FormQuestion(
            label=label, kind=QuestionKind.SINGLE_SELECT, required=required, options=options
        ),
        picked,
        None,
    )


def multi_choice(
    label: str, options: tuple[str, ...], picked: str, required: bool = True
) -> ComposedAnswer:
    return ComposedAnswer(
        FormQuestion(
            label=label, kind=QuestionKind.MULTI_SELECT, required=required, options=options
        ),
        picked,
        None,
    )


def _entry_block(sheet: str, marker: str) -> str:
    """Return the single entry paragraph that starts with `marker`, isolated from the rest."""
    entries = sheet.split("\n\n")
    matches = [e for e in entries if e.startswith(marker)]
    assert len(matches) == 1, f"expected exactly one entry starting with {marker!r}, got {matches}"
    return matches[0]


def test_every_question_is_numbered_out_of_the_total():
    sheet = render_sheet([answered("First Name", "Alberto"), gap("Salary", "no basis")], **HEADER)
    # Pin the number to the RIGHT question, not just present anywhere in the sheet.
    first = _entry_block(sheet, "[1/2]")
    second = _entry_block(sheet, "[2/2]")
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
    first = _entry_block(sheet, "[1/2]")
    second = _entry_block(sheet, "[2/2]")
    assert "(required)" in first.splitlines()[0]
    assert "(required)" not in second.splitlines()[0]


def test_an_optional_question_is_not_marked_required():
    sheet = render_sheet([answered("Headline", "x", required=False)], **HEADER)
    assert "(required)" not in sheet
    # The header line itself must not carry any parenthetical mark for an optional field.
    entry = _entry_block(sheet, "[1/1]")
    assert entry.splitlines()[0] == "[1/1] Headline"


def test_a_gap_is_shouted_with_its_reason_attached_to_its_own_question():
    sheet = render_sheet(
        [answered("First Name", "Alberto"), gap("Salary", "no basis in your profile to answer")],
        **HEADER,
    )
    salary_entry = _entry_block(sheet, "[2/2] Salary")
    assert "!! I DON'T KNOW" in salary_entry
    assert "no basis in your profile to answer" in salary_entry
    # The answered question must not itself be flagged as a gap.
    name_entry = _entry_block(sheet, "[1/2] First Name")
    assert "!! I DON'T KNOW" not in name_entry


def test_a_choice_shows_the_pick_distinguished_from_the_alternatives():
    sheet = render_sheet([choice("Sponsorship?", ("No", "Yes, now"), "Yes, now")], **HEADER)
    entry = _entry_block(sheet, "[1/1]")
    lines = entry.splitlines()
    assert "> Yes, now" in lines
    # "No" (the alternative) must appear in the "not chosen" line, never as the chosen pick
    # — regression guard for the old "options:" label, which read as if "No" were the answer.
    assert "> No" not in lines
    assert any(line.startswith("  not chosen:") and "No" in line for line in lines)


def test_a_choice_with_no_remaining_alternative_omits_the_not_chosen_line():
    sheet = render_sheet([choice("Confirm?", ("Yes",), "Yes")], **HEADER)
    entry = _entry_block(sheet, "[1/1]")
    lines = entry.splitlines()
    assert "> Yes" in lines
    assert not any(line.startswith("  not chosen:") for line in lines)


def test_a_single_select_question_is_marked_pick_one_of_n():
    sheet = render_sheet([choice("Sponsorship?", ("No", "Yes, now", "Later"), "No")], **HEADER)
    entry = _entry_block(sheet, "[1/1]")
    assert "pick 1 of 3" in entry.splitlines()[0]


def test_a_multi_select_question_is_marked_pick_any_of_n_not_pick_one():
    sheet = render_sheet(
        [multi_choice("Which languages?", ("Python", "Ruby", "Elixir"), "Python")], **HEADER
    )
    entry = _entry_block(sheet, "[1/1]")
    header_line = entry.splitlines()[0]
    assert "pick any of 3" in header_line
    assert "pick 1 of" not in header_line


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

    name = _entry_block(sheet, "[1/4] First Name")
    headline = _entry_block(sheet, "[2/4] Headline")
    auth = _entry_block(sheet, "[3/4] Work authorization?")
    salary = _entry_block(sheet, "[4/4] Expected salary")

    assert "(required)" in name.splitlines()[0]
    assert "(required)" not in headline.splitlines()[0]
    assert "> Yes" in auth.splitlines()
    assert "not chosen: No" in auth
    assert "!! I DON'T KNOW" in salary
    assert "no basis in your profile to answer" in salary
    assert "1 of 4 need you" in sheet
