"""The standard fields a Recruitee offer always asks, switched on and off by its flags."""

from moonlighter.application.assisted.questions import QuestionKind
from moonlighter.application.assisted.sources.recruitee import (
    parse_recruitee_questions,
)

from tests.application.assisted.sources.recruitee.recruitee_offers import PAYLOAD


def test_an_offer_synthesizes_the_standard_fields_the_form_always_asks():
    # The offers API publishes only the *custom* questions, but the real form
    # always asks the standard candidate fields, with their presence declared
    # by the options_* flags. A sheet without them claims "nothing left for
    # you" over a form that still wants name, email and a CV — found live on
    # the Curotec gate application (2026-08-13), where the tracking alias had
    # no email question to land on.
    questions = parse_recruitee_questions(PAYLOAD)
    labels = [question.label for question in questions]
    assert labels == [
        "Full name",
        "Email",
        "Phone",
        "CV",
        "Cover letter",
        PAYLOAD["offer"]["locations_question"],
    ]
    by_label = {question.label: question for question in questions}
    assert by_label["Full name"].required is True
    assert by_label["Email"].required is True
    assert by_label["Phone"].required is True  # options_phone: required
    assert by_label["CV"].kind is QuestionKind.FILE
    assert by_label["CV"].required is True  # options_cv: required
    assert by_label["Cover letter"].kind is QuestionKind.LONG_TEXT
    assert by_label["Cover letter"].required is False  # options_cover_letter: optional
    # options_photo is "off" in the fixture: no Photo question.
    assert "Photo" not in by_label


def test_off_flags_suppress_their_standard_fields():
    payload = {
        "offer": {
            "options_phone": "off",
            "options_cv": "off",
            "options_cover_letter": "off",
            "options_photo": "off",
        }
    }
    labels = [question.label for question in parse_recruitee_questions(payload)]
    assert labels == ["Full name", "Email"]


def test_missing_flags_synthesize_only_name_and_email():
    # An older or partial payload without options_* flags: name and email are
    # the only fields every Recruitee form carries unconditionally.
    labels = [question.label for question in parse_recruitee_questions({"offer": {}})]
    assert labels == ["Full name", "Email"]


def test_a_photo_flag_on_yields_a_file_question():
    payload = {"offer": {"options_photo": "optional"}}
    by_label = {question.label: question for question in parse_recruitee_questions(payload)}
    assert by_label["Photo"].kind is QuestionKind.FILE
    assert by_label["Photo"].required is False
