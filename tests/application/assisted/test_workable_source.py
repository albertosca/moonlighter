import json
from pathlib import Path

import httpx
from moonlighter.application.assisted.questions import QuestionKind
from moonlighter.application.assisted.sources.base import SourceMatch, questions_or_empty
from moonlighter.application.assisted.sources.workable import (
    WorkableSource,
    fetch_workable_questions,
    parse_workable_form,
    shortcode_from_url,
)

FIXTURES = Path(__file__).parent / "fixtures"
SEEQ = json.loads((FIXTURES / "workable_form_seeq.json").read_text())
DEVSU = json.loads((FIXTURES / "workable_form_devsu.json").read_text())


def _labelled_fields(payload):
    return [field for section in payload for field in section["fields"] if field.get("label")]


def _by_label(questions, label):
    return next(question for question in questions if question.label == label)


def test_every_labelled_field_becomes_a_question():
    assert len(parse_workable_form(SEEQ)) == len(_labelled_fields(SEEQ))


def test_required_is_copied_per_field():
    questions = parse_workable_form(SEEQ)
    assert _by_label(questions, "Email").required is True
    assert _by_label(questions, "Summary").required is False


def test_a_dropdown_carries_its_option_values():
    country = _by_label(parse_workable_form(DEVSU), "Country of Residence")
    assert country.kind is QuestionKind.SINGLE_SELECT
    assert country.options[:2] == ("Argentina", "Bolivia")


def test_a_single_option_multiple_is_a_single_select():
    consent = next(
        question
        for question in parse_workable_form(DEVSU)
        if question.label.startswith("During this application")
    )
    assert consent.kind is QuestionKind.SINGLE_SELECT
    assert consent.options == ("Yes", "No")


def test_a_multi_option_multiple_is_a_multi_select():
    payload = [
        {
            "fields": [
                {
                    "label": "Stacks",
                    "type": "multiple",
                    "singleOption": False,
                    "required": True,
                    "options": [{"value": "Elixir"}, {"value": "Ruby"}],
                }
            ]
        }
    ]
    [question] = parse_workable_form(payload)
    assert question.kind is QuestionKind.MULTI_SELECT
    assert question.options == ("Elixir", "Ruby")


def test_types_map_to_kinds():
    questions = parse_workable_form(SEEQ) + parse_workable_form(DEVSU)
    assert _by_label(questions, "Resume").kind is QuestionKind.FILE
    assert _by_label(questions, "Summary").kind is QuestionKind.LONG_TEXT
    assert _by_label(questions, "Phone").kind is QuestionKind.TEXT
    assert _by_label(questions, "Desired Monthly Salary in USD").kind is QuestionKind.TEXT
    assert _by_label(questions, "Education").kind is QuestionKind.LONG_TEXT


def _boolean_labels(payload):
    return [field["label"] for field in _labelled_fields(payload) if field["type"] == "boolean"]


def test_every_boolean_field_is_a_yes_no_single_select():
    # Workable's `boolean` is its Yes/No question type: the page renders it as
    # YES/NO buttons (Seeq, live 2026-10-05), whether the label ends in "?" or
    # not ("Expertise in building large React applications with TypeScript"),
    # and Devsu's label even says "Selecting 'No' means...". Lever and paste
    # give the same questions as single_select ("Yes", "No"); so does Workable.
    for payload in (SEEQ, DEVSU):
        questions = parse_workable_form(payload)
        labels = _boolean_labels(payload)
        assert labels, "fixture must contain boolean fields"
        for label in labels:
            question = _by_label(questions, label)
            assert question.kind is QuestionKind.SINGLE_SELECT, label
            assert question.options == ("Yes", "No"), label


def test_a_boolean_field_keeps_workables_own_option_labels():
    payload = [
        {
            "fields": [
                {
                    "label": "Are you based in Brazil?",
                    "type": "boolean",
                    "required": True,
                    "options": [{"name": "Y", "value": "Sí"}, {"name": "N", "value": "No"}],
                }
            ]
        }
    ]
    [question] = parse_workable_form(payload)
    assert question.kind is QuestionKind.SINGLE_SELECT
    assert question.options == ("Sí", "No")
    assert question.required is True


def test_a_boolean_field_without_options_answers_in_the_question_language():
    payload = [{"fields": [{"label": "Você possui CNPJ ativo?", "type": "boolean"}]}]
    [question] = parse_workable_form(payload)
    assert question.options == ("Sim", "Não")
    assert question.required is False


def test_an_unknown_type_falls_back_to_long_text():
    [question] = parse_workable_form(
        [{"fields": [{"label": "Pick a date", "type": "date", "required": True}]}]
    )
    assert question.kind is QuestionKind.LONG_TEXT


def test_a_dropdown_without_options_degrades_to_long_text():
    [question] = parse_workable_form(
        [{"fields": [{"label": "Country", "type": "dropdown", "required": True, "options": []}]}]
    )
    assert question.kind is QuestionKind.LONG_TEXT
    assert question.options == ()


def test_a_payload_that_is_not_a_section_list_has_no_form():
    assert parse_workable_form({"error": "not found"}) == []


def test_malformed_sections_and_fields_are_skipped():
    payload = ["not a section", {"fields": ["not a field", {"type": "text"}]}]
    assert parse_workable_form(payload) == []


async def test_workable_publishes_no_separate_required_fields():
    async with httpx.AsyncClient() as client:
        source = WorkableSource()
        assert await source.required_fields(SourceMatch(source, ("x",)), client) == ()


def test_shortcode_from_url():
    assert shortcode_from_url("https://apply.workable.com/j/1378093793/apply") == "1378093793"
    assert shortcode_from_url("https://apply.workable.com/devsu/j/C3DABE6A92/") == "C3DABE6A92"
    assert shortcode_from_url("https://careers.acme.com/j/123") is None


async def test_fetch_reads_the_form_endpoint():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=SEEQ)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        questions = await fetch_workable_questions("1378093793", client)
    assert seen == ["https://apply.workable.com/api/v1/jobs/1378093793/form"]
    assert len(questions) == len(_labelled_fields(SEEQ))


async def test_a_non_200_means_no_form(caplog):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(404))
    ) as client:
        assert await fetch_workable_questions("x", client) == []
    [record] = [
        record
        for record in caplog.records
        if record.name == "moonlighter.application.assisted.sources.workable"
    ]
    assert record.levelname == "WARNING"
    assert "404" in record.getMessage()


async def test_a_200_html_body_means_no_form():
    # Cloudflare answers challenges with 200 + HTML; that is not a form.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>Just a moment...</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        match = SourceMatch(WorkableSource(), ("x",))
        assert await questions_or_empty(match, client) == []
