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


def test_an_offer_without_extra_questions_yields_only_the_location_question():
    # The committed fixture has empty open_questions and dynamic_fields; the
    # location question is still a real, required question on the form.
    questions = parse_recruitee_questions(PAYLOAD)
    assert [q.label for q in questions] == [PAYLOAD["offer"]["locations_question"]]


def test_an_open_question_becomes_a_long_text_question():
    payload = {"offer": {"open_questions": [{"body": "Why us?", "required": True}]}}
    questions = parse_recruitee_questions(payload)
    assert questions[0].label == "Why us?"
    assert questions[0].kind is QuestionKind.LONG_TEXT
    assert questions[0].required is True


def test_a_multiple_choice_open_question_carries_its_options():
    payload = {
        "offer": {
            "open_questions": [
                {
                    "body": "Seniority?",
                    "required": True,
                    "kind": "multi_choice",
                    "options": ["Mid", "Senior"],
                }
            ]
        }
    }
    question = parse_recruitee_questions(payload)[0]
    assert question.kind is QuestionKind.SINGLE_SELECT
    assert question.options == ("Mid", "Senior")


def test_a_multiple_choice_question_without_options_degrades_to_text():
    payload = {"offer": {"open_questions": [{"body": "Seniority?", "kind": "multi_choice"}]}}
    assert parse_recruitee_questions(payload)[0].kind is QuestionKind.TEXT


def test_an_empty_payload_yields_nothing():
    assert parse_recruitee_questions({}) == []


def test_a_question_without_a_label_is_dropped():
    payload = {"offer": {"open_questions": [{"required": True}]}}
    assert parse_recruitee_questions(payload) == []


def test_a_non_dict_entry_in_the_question_list_is_skipped():
    payload = {"offer": {"dynamic_fields": ["not a question"]}}
    assert parse_recruitee_questions(payload) == []


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
