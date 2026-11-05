"""Reading a Lever apply page: card templates, standard fields and the unreadable cases."""

import pytest
from moonlighter.application.assisted.questions import QuestionKind
from moonlighter.application.assisted.sources.lever import (
    parse_lever_form,
)

from tests.application.assisted.sources.lever.lever_pages import (
    PAGE,
    by_label,
    card_fields,
    card_page,
)


def test_standard_fields_carry_the_asterisk_as_required():
    questions = parse_lever_form(PAGE)
    assert by_label(questions, "Full name").required is True
    assert by_label(questions, "Current location").required is True
    assert by_label(questions, "Phone").required is False


def test_the_resume_field_is_a_file():
    resume = by_label(parse_lever_form(PAGE), "Resume/CV")
    assert resume.kind is QuestionKind.FILE
    assert resume.required is True


def test_every_card_field_becomes_one_question():
    questions = parse_lever_form(PAGE)
    card_labels = {field["text"] for field in card_fields(PAGE)}
    assert card_labels <= {question.label for question in questions}
    standard_labels = {"Resume/CV", "Full name", "Email", "Phone", "Current location"}
    assert standard_labels <= {question.label for question in questions}
    assert len(questions) == len({question.label for question in questions})


def test_card_types_map_to_kinds_with_options():
    languages = by_label(parse_lever_form(PAGE), "Language Skill(s) (Check all that apply)")
    assert languages.kind is QuestionKind.MULTI_SELECT
    assert languages.required is True
    assert "English (ENG)" in languages.options


@pytest.mark.parametrize(
    ("card_type", "expected"),
    [
        ("text", QuestionKind.TEXT),
        ("textarea", QuestionKind.LONG_TEXT),
        ("dropdown", QuestionKind.SINGLE_SELECT),
        ("multiple-choice", QuestionKind.SINGLE_SELECT),
        ("multiple-select", QuestionKind.MULTI_SELECT),
        ("something-new", QuestionKind.LONG_TEXT),
    ],
)
def test_each_card_type(card_type, expected):
    card = {
        "fields": [
            {
                "type": card_type,
                "text": "Q",
                "required": False,
                "options": [{"text": "A"}, {"text": "B"}],
            }
        ]
    }
    [question] = parse_lever_form(card_page(card))
    assert question.kind is expected


def test_a_choice_card_without_options_degrades_to_long_text():
    card = {"fields": [{"type": "dropdown", "text": "Q", "required": True, "options": []}]}
    [question] = parse_lever_form(card_page(card))
    assert question.kind is QuestionKind.LONG_TEXT


def test_a_malformed_card_makes_the_form_unreadable():
    page = PAGE.replace('name="cards[', 'data-broken="1" value="{not json" name="cards[', 1)
    with pytest.raises(ValueError):  # noqa: PT011 - the message is json's own decode error
        parse_lever_form(page)


def test_the_real_page_reads_every_custom_question_from_its_cards():
    custom_questions_in_markup = PAGE.count('class="application-question custom-question"')
    assert custom_questions_in_markup == 12
    card_labels = {field["text"] for field in card_fields(PAGE)}
    read_from_cards = [
        question for question in parse_lever_form(PAGE) if question.label in card_labels
    ]
    assert len(read_from_cards) == custom_questions_in_markup


def test_custom_questions_in_the_markup_without_a_card_template_make_the_form_unreadable():
    # The drift the markup can suffer silently: Lever renames `[baseTemplate]`, every
    # card vanishes, and the sheet would claim a complete form of standard fields.
    page = PAGE.replace("[baseTemplate]", "[template]")
    with pytest.raises(ValueError, match="12 custom questions in the markup but 0 were read"):
        parse_lever_form(page)


def test_a_card_without_fields_makes_the_form_unreadable():
    with pytest.raises(ValueError, match="a Lever card template has no list of fields"):
        parse_lever_form(card_page({"questions": []}, custom_questions=0))


def test_a_card_whose_fields_are_not_a_list_makes_the_form_unreadable():
    with pytest.raises(ValueError, match="a Lever card template has no list of fields"):
        parse_lever_form(card_page({"fields": 5}, custom_questions=0))


def test_the_additional_information_textarea_is_an_optional_long_text_question():
    # It sits in div.application-additional, outside every li.application-question:
    # the cover-letter slot, which Alberto always fills even though it is optional.
    questions = parse_lever_form(PAGE)
    additional = by_label(questions, "Additional information")
    assert additional.kind is QuestionKind.LONG_TEXT
    assert additional.required is False
    assert questions[-1] is additional


def test_a_page_without_the_comments_textarea_has_no_additional_information_question():
    page = PAGE.replace('name="comments"', 'name="something-else"')
    labels = {question.label for question in parse_lever_form(page)}
    assert "Additional information" not in labels


def test_a_page_without_a_form_has_no_questions():
    assert parse_lever_form("<html><body>This posting is closed.</body></html>") == []


def test_a_card_that_is_not_an_object_makes_the_form_unreadable():
    page = '<form><input value="[1, 2]" name="cards[1][baseTemplate]"></form>'
    with pytest.raises(ValueError, match="a Lever card template is not a JSON object"):
        parse_lever_form(page)


def test_card_fields_without_text_are_skipped():
    card = {"fields": ["not a field", {"type": "text", "required": True}]}
    assert parse_lever_form(card_page(card)) == []


def test_an_empty_standard_label_is_skipped():
    page = '<ul><li class="application-question"><div class="application-label"></div><div>x</div></li></ul>'
    assert parse_lever_form(page) == []
