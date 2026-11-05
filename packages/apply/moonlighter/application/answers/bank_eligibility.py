"""Which questions the cross-job answer bank may hold, and the key it files them under."""

import re

from moonlighter.application.assisted.questions import QuestionKind

_BANK_ELIGIBLE_KINDS = frozenset(
    {QuestionKind.TEXT, QuestionKind.BOOLEAN, QuestionKind.SINGLE_SELECT, QuestionKind.MULTI_SELECT}
)
_WHITESPACE = re.compile(r"\s+")
_TRAILING_PUNCTUATION = re.compile(r"[?:*]+$")

# Demographic/EEO categories and third-party references. Over-matching is
# deliberate and cheap in this direction (PT-BR "preferências" contains
# "referências", so it matches too): a false positive costs one ordinary LLM
# call, a false negative persists a hallucinated answer across companies.
#
# The second half of this list was added 2026-09-14 after a review measured the
# full leak path open for every one of them: the question reached the LLM, the
# model invented an answer, and because promote_application checks the same
# function, the invention was banked and replayed at the next company.
# "Ethnicity" is not hypothetical — it is a real Greenhouse label.
#
# Two word boundaries here are load-bearing, both measured against real fields:
# without `\b`, "pronoun" swallows "How do you pronounce your name?" and PT-BR
# "idade" swallows "Cidade" — which field_map answers today.
_SENSITIVE_LABEL = re.compile(
    r"gender|g[êe]nero|\brace\b|ra[çc]a|hispanic|latino|\bveteran\b|veteran[oa]|"
    r"disabilit|defici[êe]nc|\breferences?\b|refer[êe]ncias?|"
    r"ethnic|etnia|\bpronouns?\b|\bpronomes?\b|"
    r"sexual\s+orientation|orienta[çc][ãa]o\s+sexual|"
    r"\bage\b|\bidade\b|date\s+of\s+birth|nascimento|"
    r"marital|estado\s+civil|religi|lgbt",
    re.IGNORECASE,
)


def is_bank_eligible(kind: QuestionKind) -> bool:
    return kind in _BANK_ELIGIBLE_KINDS


def is_sensitive_label(label: str) -> bool:
    """A label naming a demographic/EEO category or third-party references.

    Never eligible for the cross-job bank regardless of question kind, because
    nothing deterministic stops the LLM from guessing an answer to a label
    like this even though the underlying data is deliberately excluded from
    its prompt (profile.py's profile_for_answers). A hallucinated answer here
    must not persist into a table shared across every future company.
    """
    return bool(_SENSITIVE_LABEL.search(label))


def normalize_question(label: str) -> str:
    text = _WHITESPACE.sub(" ", label.strip()).lower()
    return _TRAILING_PUNCTUATION.sub("", text).strip()
