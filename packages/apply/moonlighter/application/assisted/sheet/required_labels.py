"""Tie the fields a source says are required to the questions read from a paste."""

import re
from dataclasses import replace

from moonlighter.application.assisted.questions import FormQuestion

# Keywords that tie a required-field label (from a source's required_fields)
# to a question read from a paste, matched as whole words, EN and PT-BR.
REQUIRED_KEYWORDS: dict[str, tuple[str, ...]] = {
    "LinkedIn": ("linkedin",),
    "Salary expectation": (
        "salary",
        "salário",
        "salario",
        "salarial",
        "pretensão",
        "pretensao",
        "remuneração",
        "remuneracao",
    ),
    "CV": ("cv", "currículo", "curriculo", "curriculum", "resume", "résumé"),
    "Location": ("location", "localização", "localizacao", "cidade"),
}


def mark_required(
    questions: list[FormQuestion], required_labels: tuple[str, ...]
) -> list[FormQuestion]:
    keywords = [
        keyword
        for label in required_labels
        for keyword in REQUIRED_KEYWORDS.get(label, (label.lower(),))
    ]
    patterns = [re.compile(rf"\b{re.escape(keyword)}\b") for keyword in keywords]
    return [
        replace(question, required=True)
        if not question.required
        and any(pattern.search(question.label.lower()) for pattern in patterns)
        else question
        for question in questions
    ]
