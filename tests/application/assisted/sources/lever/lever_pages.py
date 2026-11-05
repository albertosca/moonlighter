"""The Lever apply page and the helpers that read or fake its card templates."""

import html
import json
import re

from tests.application.assisted.sources.fixture_files import FIXTURES_DIRECTORY

PAGE = (FIXTURES_DIRECTORY / "lever_apply_palantir.html").read_text()


def card_fields(page):
    fields = []
    for tag in re.findall(r"<input[^>]*baseTemplate[^>]*>", page):
        value = re.search(r'value="([^"]*)"', tag).group(1)
        fields.extend(json.loads(html.unescape(value))["fields"])
    return fields


def by_label(questions, label):
    return next(question for question in questions if question.label == label)


def card_page(card, custom_questions=None):
    """A page carrying one card template and, like the real page, one custom-question
    `li` per card field with text (or `custom_questions` of them when given)."""
    if custom_questions is None:
        custom_questions = sum(
            1 for field in card.get("fields") or [] if isinstance(field, dict) and field.get("text")
        )
    value = html.escape(json.dumps(card), quote=True)
    items = '<li class="application-question custom-question"></li>' * custom_questions
    return (
        f'<form><input type="hidden" value="{value}" name="cards[1][baseTemplate]">'
        f"<ul>{items}</ul></form>"
    )
