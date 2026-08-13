import json
from pathlib import Path

import httpx
import pytest
from moonlighter.application.assisted.questions import QuestionKind
from moonlighter.application.assisted.sources.recruitee import (
    fetch_recruitee_questions,
    parse_recruitee_questions,
    slug_and_offer_from_url,
)

PAYLOAD = json.loads((Path(__file__).parent / "fixtures" / "recruitee_offer.json").read_text())
PAYLOAD_WITH_CHOICE = json.loads(
    (Path(__file__).parent / "fixtures" / "recruitee_offer_with_choice.json").read_text()
)
PAYLOAD_WITH_BOOLEAN_AND_DATE = json.loads(
    (Path(__file__).parent / "fixtures" / "recruitee_offer_with_boolean_and_date.json").read_text()
)


def test_an_offer_synthesizes_the_standard_fields_the_form_always_asks():
    # The offers API publishes only the *custom* questions, but the real form
    # always asks the standard candidate fields, with their presence declared
    # by the options_* flags. A sheet without them claims "nothing left for
    # you" over a form that still wants name, email and a CV — found live on
    # the Curotec gate application (2026-08-13), where the tracking alias had
    # no email question to land on.
    questions = parse_recruitee_questions(PAYLOAD)
    labels = [q.label for q in questions]
    assert labels == [
        "Full name",
        "Email",
        "Phone",
        "CV",
        "Cover letter",
        PAYLOAD["offer"]["locations_question"],
    ]
    by_label = {q.label: q for q in questions}
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
    labels = [q.label for q in parse_recruitee_questions(payload)]
    assert labels == ["Full name", "Email"]


def test_missing_flags_synthesize_only_name_and_email():
    # An older or partial payload without options_* flags: name and email are
    # the only fields every Recruitee form carries unconditionally.
    labels = [q.label for q in parse_recruitee_questions({"offer": {}})]
    assert labels == ["Full name", "Email"]


def test_a_photo_flag_on_yields_a_file_question():
    payload = {"offer": {"options_photo": "optional"}}
    by_label = {q.label: q for q in parse_recruitee_questions(payload)}
    assert by_label["Photo"].kind is QuestionKind.FILE
    assert by_label["Photo"].required is False


def test_an_open_question_becomes_a_long_text_question():
    payload = {"offer": {"open_questions": [{"body": "Why us?", "required": True}]}}
    questions = parse_recruitee_questions(payload)
    question = next(q for q in questions if q.label == "Why us?")
    assert question.kind is QuestionKind.LONG_TEXT
    assert question.required is True


def test_a_multi_choice_question_reads_its_options_from_a_live_offer():
    # Live fixture: a real multi_choice question whose "options" key is an
    # empty dict; the two actual alternatives live in open_question_options.
    questions = parse_recruitee_questions(PAYLOAD_WITH_CHOICE)
    question = next(q for q in questions if q.kind is QuestionKind.SINGLE_SELECT)
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
    question = next(q for q in parse_recruitee_questions(payload) if q.label == "Seniority?")
    assert question.options == ("Mid", "Senior")


def test_a_multi_choice_question_without_open_question_options_degrades_to_text():
    payload = {"offer": {"open_questions": [{"body": "Seniority?", "kind": "multi_choice"}]}}
    question = next(q for q in parse_recruitee_questions(payload) if q.label == "Seniority?")
    assert question.kind is QuestionKind.TEXT


def test_reading_the_empty_options_dict_never_yields_a_choice_question():
    # Regression guard: "options" on real data is always {}, not a list. A
    # parser that fell back to reading it must not manufacture a select.
    payload = {
        "offer": {"open_questions": [{"body": "Seniority?", "kind": "multi_choice", "options": {}}]}
    }
    question = next(q for q in parse_recruitee_questions(payload) if q.label == "Seniority?")
    assert question.kind is QuestionKind.TEXT
    assert question.options == ()


def test_a_boolean_question_maps_to_boolean_with_no_options():
    questions = parse_recruitee_questions(PAYLOAD_WITH_BOOLEAN_AND_DATE)
    booleans = [
        q for q in questions if q.label.startswith("Do you require") or "Netherlands" in q.label
    ]
    assert len(booleans) == 2
    assert all(q.kind is QuestionKind.BOOLEAN for q in booleans)
    assert all(q.options == () for q in booleans)


def test_a_date_question_maps_to_text():
    questions = parse_recruitee_questions(PAYLOAD_WITH_BOOLEAN_AND_DATE)
    dates = [q for q in questions if "start" in q.label]
    assert len(dates) == 1
    assert dates[0].kind is QuestionKind.TEXT


def test_an_unrecognised_kind_falls_back_to_text_instead_of_vanishing():
    payload = {"offer": {"open_questions": [{"body": "Odd one", "kind": "some_new_widget"}]}}
    questions = parse_recruitee_questions(payload)
    assert [q.label for q in questions] == ["Full name", "Email", "Odd one"]
    assert questions[-1].kind is QuestionKind.TEXT


def test_an_empty_payload_yields_nothing():
    assert parse_recruitee_questions({}) == []


def test_a_question_without_a_label_is_dropped():
    payload = {"offer": {"open_questions": [{"required": True}]}}
    assert [q.label for q in parse_recruitee_questions(payload)] == ["Full name", "Email"]


def test_a_non_dict_entry_in_the_question_list_is_skipped():
    payload = {"offer": {"dynamic_fields": ["not a question"]}}
    assert [q.label for q in parse_recruitee_questions(payload)] == ["Full name", "Email"]


def test_slug_and_offer_are_read_from_a_recruitee_url():
    assert slug_and_offer_from_url("https://curotec.recruitee.com/o/senior-android/c/new") == (
        "curotec",
        "senior-android",
    )


def test_a_custom_domain_is_not_matched():
    # Most Recruitee customers use their own domain; those go through pasting.
    assert slug_and_offer_from_url("https://jobs.channable.com/o/x") is None


@pytest.mark.asyncio
async def test_a_failed_request_yields_no_questions():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_recruitee_questions("curotec", "x", client) == []


@pytest.mark.asyncio
async def test_a_successful_request_returns_the_parsed_questions():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=PAYLOAD)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        questions = await fetch_recruitee_questions("curotec", "x", client)
    assert questions == parse_recruitee_questions(PAYLOAD)
