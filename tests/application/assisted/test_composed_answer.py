"""Pins that a composed answer is either answered or a gap, never both or neither."""

import pytest
from moonlighter.application.assisted.composer import ComposedAnswer
from moonlighter.application.assisted.questions import FormQuestion, QuestionKind


def test_a_composed_answer_cannot_be_both_answered_and_a_gap():
    question = FormQuestion(label="First Name", kind=QuestionKind.TEXT, required=True)
    with pytest.raises(ValueError, match="never both or neither"):
        ComposedAnswer(question, "Alberto", "no basis in your profile to answer")


def test_a_composed_answer_cannot_be_neither_answered_nor_a_gap():
    question = FormQuestion(label="First Name", kind=QuestionKind.TEXT, required=True)
    with pytest.raises(ValueError, match="never both or neither"):
        ComposedAnswer(question, None, None)
