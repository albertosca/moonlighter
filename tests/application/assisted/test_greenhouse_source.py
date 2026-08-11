import json
from pathlib import Path

import httpx
import pytest
from moonlighter.application.assisted.questions import QuestionKind
from moonlighter.application.assisted.sources.greenhouse import (
    board_and_job_from_url,
    fetch_greenhouse_questions,
    parse_greenhouse_questions,
)

PAYLOAD = json.loads((Path(__file__).parent / "fixtures" / "greenhouse_job.json").read_text())


def test_parses_every_question_in_the_payload():
    questions = parse_greenhouse_questions(PAYLOAD)
    assert len(questions) == len(PAYLOAD["questions"])


def test_a_select_carries_its_options_verbatim():
    questions = parse_greenhouse_questions(PAYLOAD)
    selects = [q for q in questions if q.kind is QuestionKind.SINGLE_SELECT]
    assert selects, "fixture must contain at least one select"
    assert all(q.options for q in selects)


def test_a_file_question_becomes_a_file_kind():
    questions = parse_greenhouse_questions(PAYLOAD)
    assert any(q.kind is QuestionKind.FILE for q in questions)


def test_an_unknown_field_type_falls_back_to_text_instead_of_vanishing():
    payload = {
        "questions": [
            {
                "label": "Odd one",
                "required": False,
                "fields": [{"type": "some_new_widget", "values": []}],
            }
        ]
    }
    questions = parse_greenhouse_questions(payload)
    assert len(questions) == 1
    assert questions[0].kind is QuestionKind.TEXT


def test_a_select_with_no_options_degrades_to_text_instead_of_raising():
    payload = {
        "questions": [
            {
                "label": "Empty select",
                "required": False,
                "fields": [{"type": "multi_value_single_select", "values": []}],
            }
        ]
    }
    questions = parse_greenhouse_questions(payload)
    assert len(questions) == 1
    assert questions[0].kind is QuestionKind.TEXT


def test_a_question_without_a_label_is_dropped():
    payload = {"questions": [{"required": True, "fields": [{"type": "input_text"}]}]}
    assert parse_greenhouse_questions(payload) == []


def test_board_and_job_are_read_from_a_job_board_url():
    assert board_and_job_from_url("https://job-boards.greenhouse.io/gitlab/jobs/8503792002") == (
        "gitlab",
        "8503792002",
    )


def test_a_url_that_is_not_greenhouse_yields_nothing():
    assert board_and_job_from_url("https://example.com/careers/1") is None


@pytest.mark.asyncio
async def test_fetch_returns_the_parsed_questions():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=PAYLOAD)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        questions = await fetch_greenhouse_questions("gitlab", "1", client)
    assert len(questions) == len(PAYLOAD["questions"])


@pytest.mark.asyncio
async def test_a_failed_request_yields_no_questions_rather_than_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "Job not found"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_greenhouse_questions("gitlab", "1", client) == []


@pytest.mark.asyncio
async def test_a_non_dict_body_yields_no_questions():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_greenhouse_questions("gitlab", "1", client) == []
