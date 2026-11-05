import pytest
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind


def test_a_plain_question_has_no_options():
    question = FormQuestion(label="First Name", kind=QuestionKind.TEXT, required=True)
    assert question.options == ()
    assert question.is_choice is False


def test_a_select_question_reports_itself_as_a_choice():
    question = FormQuestion(
        label="Will you require sponsorship?",
        kind=QuestionKind.SINGLE_SELECT,
        required=True,
        options=("No", "Yes, now"),
    )
    assert question.is_choice is True


def test_a_choice_question_without_options_is_rejected():
    # A select with no options cannot be answered, and silently accepting it is
    # how an unanswerable question reaches the sheet looking answerable.
    with pytest.raises(ValueError, match="options"):
        FormQuestion(label="Country", kind=QuestionKind.SINGLE_SELECT, required=True)
