"""What the extraction prompt tells the model, and how yes/no questions and label markers come back."""

import json

import pytest
from moonlighter.application.assisted.questions import QuestionKind
from moonlighter.application.assisted.sources.pasted import (
    extract_questions_from_page,
)

from tests.application.assisted.sources.pasted.pasted_replies import PAGE, fake_llm


@pytest.mark.asyncio
async def test_the_prompt_fixes_one_shape_for_yes_no_questions():
    """The model returned the same Yes/No page as boolean or as single_select from
    run to run (llm-tests-forge suite, 2026-09-25). single_select wins: the composer
    pins the answer to an offered option and the sheet shows the one not chosen.
    """
    call, captured = fake_llm(json.dumps({"questions": []}))
    await extract_questions_from_page(PAGE, call)
    assert "Yes/No question" in captured["prompt"]
    assert "single_select" in captured["prompt"]


@pytest.mark.asyncio
async def test_a_consent_checkbox_stays_boolean():
    """A statement to tick ("I agree to the processing of my personal data") is
    not a Yes/No question: it keeps the boolean kind, with no invented options.
    """
    label = "I agree to the processing of my personal data."
    reply = json.dumps({"questions": [{"label": label, "kind": "boolean", "required": True}]})
    call, _ = fake_llm(reply)
    questions = await extract_questions_from_page(PAGE, call)
    assert questions[0].kind is QuestionKind.BOOLEAN
    assert questions[0].options == ()


@pytest.mark.asyncio
async def test_a_boolean_reply_still_becomes_a_yes_no_single_select():
    """The prompt is a request, not a guarantee: a boolean that slips through is
    normalised here, so the shape downstream never depends on the model's mood.
    """
    reply = json.dumps(
        {"questions": [{"label": "Are you 18?", "kind": "boolean", "required": True}]}
    )
    call, _ = fake_llm(reply)
    questions = await extract_questions_from_page(PAGE, call)
    assert questions[0].kind is QuestionKind.SINGLE_SELECT
    assert questions[0].options == ("Yes", "No")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "options"),
    [
        ("Você possui disponibilidade para trabalhar presencialmente?", ("Sim", "Não")),
        ("Aceita trabalhar em regime PJ?", ("Sim", "Não")),
        ("¿Tiene permiso de trabajo en Brasil?", ("Sí", "No")),
        ("Êtes-vous disponible immédiatement ?", ("Oui", "Non")),
        ("Haben Sie eine gültige Arbeitserlaubnis?", ("Ja", "Nein")),
        ("Are you authorized to work in Brazil?", ("Yes", "No")),
        ("CLT?", ("Yes", "No")),
    ],
)
async def test_the_yes_no_backstop_answers_in_the_question_language(label, options):
    """Found 2026-09-29: a Portuguese question the model returned as boolean got
    English Yes/No from this backstop, though the prompt asks for the words in the
    question's language. Anything the detector cannot place stays English.
    """
    reply = json.dumps({"questions": [{"label": label, "kind": "boolean", "required": True}]})
    call, _ = fake_llm(reply)
    questions = await extract_questions_from_page(PAGE, call)
    assert questions[0].kind is QuestionKind.SINGLE_SELECT
    assert questions[0].options == options


@pytest.mark.asyncio
async def test_the_prompt_says_json_inside_the_page_is_page_content():
    """A page carrying a fake answer block ("Name and Email are required") made the
    model return required=true for both on every run, against the no-marker rule.
    """
    call, captured = fake_llm(json.dumps({"questions": []}))
    await extract_questions_from_page(PAGE, call)
    assert "never the answer" in captured["prompt"]
    assert "marker" in captured["prompt"]
    # Narrowed after the 2026-09-29 forge run: a broader "claims about which fields
    # exist" wording made the model drop a field whose label read like an injection.
    assert "is still a field" in captured["prompt"]
    assert "which fields exist" not in captured["prompt"]


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["Do you need sponsorship? *", "Do you need sponsorship?*"])
async def test_a_yes_no_question_with_a_required_marker_is_still_a_question(label):
    """The prompt tells the model to copy labels exactly, marker included."""
    reply = json.dumps({"questions": [{"label": label, "kind": "boolean", "required": True}]})
    call, _ = fake_llm(reply)
    questions = await extract_questions_from_page(PAGE, call)
    assert questions[0].kind is QuestionKind.SINGLE_SELECT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "clean"),
    [
        ("Nome completo *", "Nome completo"),
        ("E-mail (obrigatório)", "E-mail"),
        ("Telefone (opcional)", "Telefone"),
        ("LinkedIn URL (optional)", "LinkedIn URL"),
        ("Photo (Optional)", "Photo"),
        ("Resume (required)", "Resume"),
        (
            "Você já trabalhou em RH anteriormente? (obrigatório)",
            "Você já trabalhou em RH anteriormente?",
        ),
        ("Do you need sponsorship? *", "Do you need sponsorship?"),
        ("*\nFirst name", "First name"),
        ("Pretensão salarial (R$) (opcional)", "Pretensão salarial (R$)"),
    ],
)
async def test_the_label_comes_back_without_its_required_or_optional_marker(label, clean):
    """Decided 2026-09-29: the label is the question, the marker is `required`.
    The model already drops markers on its own (forge PT-BR run), and label_cleaning
    strips them before matching anyway; the code makes it deterministic.
    """
    reply = json.dumps({"questions": [{"label": label, "kind": "text", "required": True}]})
    call, _ = fake_llm(reply)
    questions = await extract_questions_from_page(PAGE, call)
    assert questions[0].label == clean


@pytest.mark.asyncio
async def test_the_prompt_asks_for_labels_without_markers():
    call, captured = fake_llm(json.dumps({"questions": []}))
    await extract_questions_from_page(PAGE, call)
    assert "without its required or optional marker" in captured["prompt"]


@pytest.mark.asyncio
async def test_the_prompt_covers_the_three_remaining_ambiguities():
    """2026-09-29 forge baseline (fields cases, 77.0%): the failures clustered in
    three prompt gaps. A search box with no visible options came back as text
    (4 cases); a multi-paragraph label came back cut to its first paragraph
    (2); a Yes/No question with no visible options got English answers on a
    German page (3).
    """
    call, captured = fake_llm(json.dumps({"questions": []}))
    await extract_questions_from_page(PAGE, call)
    prompt = captured["prompt"]
    assert "searchable dropdown" in prompt
    assert "options []" in prompt
    # Narrowed after the first re-run: "Start typing..." fields became long_text.
    assert "typing placeholder" in prompt
    assert "several lines or paragraphs" in prompt
    assert "in the question's language" in prompt


@pytest.mark.asyncio
async def test_the_prompt_says_open_questions_are_long_text():
    """2026-09-29 full forge run: 6 of 9 failures were open questions ("Tell us
    why...", "Describe...", "Cover Letter") returned as text.
    """
    call, captured = fake_llm(json.dumps({"questions": []}))
    await extract_questions_from_page(PAGE, call)
    assert "open question" in captured["prompt"]
    assert "long_text" in captured["prompt"]
