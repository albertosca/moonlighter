"""Reading an offer's own questions: kinds, options, labels and the entries that are dropped."""

from moonlighter.application.assisted.questions import QuestionKind
from moonlighter.application.assisted.sources.recruitee import (
    parse_recruitee_questions,
)

from tests.application.assisted.sources.recruitee.recruitee_offers import (
    PAYLOAD_WITH_BOOLEAN_AND_DATE,
    PAYLOAD_WITH_CHOICE,
)


def test_an_open_question_becomes_a_long_text_question():
    payload = {"offer": {"open_questions": [{"body": "Why us?", "required": True}]}}
    questions = parse_recruitee_questions(payload)
    question = next(question for question in questions if question.label == "Why us?")
    assert question.kind is QuestionKind.LONG_TEXT
    assert question.required is True


def test_a_multi_choice_question_reads_its_options_from_a_live_offer():
    # Live fixture: a real multi_choice question whose "options" key is an
    # empty dict; the two actual alternatives live in open_question_options.
    questions = parse_recruitee_questions(PAYLOAD_WITH_CHOICE)
    question = next(
        question for question in questions if question.kind is QuestionKind.SINGLE_SELECT
    )
    assert question.options == ("Yes, I am EU citizen", "No, I required a visa")


def test_multi_choice_options_are_ordered_by_position_not_list_order():
    payload = {
        "offer": {
            "open_questions": [
                {
                    "body": "Seniority?",
                    "kind": "multi_choice",
                    "open_question_options": [
                        {"body": "Senior", "position": 1},
                        {"body": "Mid", "position": 0},
                    ],
                }
            ]
        }
    }
    question = next(
        question
        for question in parse_recruitee_questions(payload)
        if question.label == "Seniority?"
    )
    assert question.options == ("Mid", "Senior")


def test_a_multi_choice_question_without_open_question_options_degrades_to_long_text():
    # LONG_TEXT, not TEXT: the two render and prompt identically, and differ only
    # in that TEXT is eligible for the cross-job answer bank. A choice question
    # whose options never arrived is of genuinely unknown shape, so it degrades
    # to the side that is never replayed at a different company. Same fix as
    # pasted.py's and greenhouse.py's structurally identical branches.
    payload = {"offer": {"open_questions": [{"body": "Seniority?", "kind": "multi_choice"}]}}
    question = next(
        question
        for question in parse_recruitee_questions(payload)
        if question.label == "Seniority?"
    )
    assert question.kind is QuestionKind.LONG_TEXT


def test_reading_the_empty_options_dict_never_yields_a_choice_question():
    # Regression guard: "options" on real data is always {}, not a list. A
    # parser that fell back to reading it must not manufacture a select.
    # The degraded kind is LONG_TEXT for the reason given in the test above.
    payload = {
        "offer": {"open_questions": [{"body": "Seniority?", "kind": "multi_choice", "options": {}}]}
    }
    question = next(
        question
        for question in parse_recruitee_questions(payload)
        if question.label == "Seniority?"
    )
    assert question.kind is QuestionKind.LONG_TEXT
    assert question.options == ()


def test_a_boolean_question_is_a_yes_no_single_select():
    # A Yes/No QUESTION has one shape whatever the source (2026-09-29): Lever
    # and paste give single_select ("Yes", "No"), so Recruitee does too. The
    # label keeps its trailing space ("Do you require a visa? ") and is still a
    # question.
    questions = parse_recruitee_questions(PAYLOAD_WITH_BOOLEAN_AND_DATE)
    yes_no = [
        question
        for question in questions
        if question.label.startswith("Do you require") or "Netherlands" in question.label
    ]
    assert len(yes_no) == 2
    assert all(question.kind is QuestionKind.SINGLE_SELECT for question in yes_no)
    assert all(question.options == ("Yes", "No") for question in yes_no)


def test_a_boolean_statement_stays_a_boolean():
    # Recruitee's rendering of `boolean` was never observed live, so the paste
    # path's rule decides: a statement to tick (a consent) is not a question.
    payload = {
        "offer": {
            "open_questions": [
                {"body": "I agree to the privacy policy.", "kind": "boolean", "required": True}
            ]
        }
    }
    question = parse_recruitee_questions(payload)[-1]
    assert question.kind is QuestionKind.BOOLEAN
    assert question.options == ()


def test_a_boolean_question_answers_in_the_question_language():
    payload = {"offer": {"open_questions": [{"body": "Você tem visto?", "kind": "boolean"}]}}
    question = parse_recruitee_questions(payload)[-1]
    assert question.options == ("Sim", "Não")


def test_a_date_question_maps_to_text():
    questions = parse_recruitee_questions(PAYLOAD_WITH_BOOLEAN_AND_DATE)
    dates = [question for question in questions if "start" in question.label]
    assert len(dates) == 1
    assert dates[0].kind is QuestionKind.TEXT


def test_an_unrecognised_kind_falls_back_to_long_text_instead_of_vanishing():
    # LONG_TEXT for the same reason as the degraded multi_choice above — and it
    # now matches the no-kind-at-all branch, which already chose LONG_TEXT: a
    # kind string we cannot read tells us no more than no kind string at all.
    payload = {"offer": {"open_questions": [{"body": "Odd one", "kind": "some_new_widget"}]}}
    questions = parse_recruitee_questions(payload)
    assert [question.label for question in questions] == ["Full name", "Email", "Odd one"]
    assert questions[-1].kind is QuestionKind.LONG_TEXT


def test_an_empty_payload_yields_nothing():
    assert parse_recruitee_questions({}) == []


def test_a_question_without_a_label_is_dropped():
    payload = {"offer": {"open_questions": [{"required": True}]}}
    assert [question.label for question in parse_recruitee_questions(payload)] == [
        "Full name",
        "Email",
    ]


def test_a_non_dict_entry_in_the_question_list_is_skipped():
    payload = {"offer": {"dynamic_fields": ["not a question"]}}
    assert [question.label for question in parse_recruitee_questions(payload)] == [
        "Full name",
        "Email",
    ]
