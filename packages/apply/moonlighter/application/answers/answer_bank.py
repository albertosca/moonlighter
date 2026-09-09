"""Cross-job cache of approved LLM answers, keyed by normalised question text.

Only questions whose kind cannot legitimately vary per posting are eligible:
TEXT, BOOLEAN, SINGLE_SELECT, MULTI_SELECT. LONG_TEXT is never eligible — it is
where an answer is most likely to be genuinely company-specific prose (a "why
this company" essay), and reusing it verbatim at a different company would
silently paste the wrong answer into a real form.

Normalisation is deliberately exact (lowercase, collapsed whitespace, no
trailing punctuation) rather than fuzzy: a screening question that "repeats
almost verbatim" across postings already collides on this key, and a miss
just costs one ordinary LLM call — never a wrong answer. Same preference
work_auth.py already states for its own NEEDS_REVIEW sentinel: a cache miss
over a wrong cache hit.
"""

import re
from datetime import datetime
from typing import Any

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
_SENSITIVE_LABEL = re.compile(
    r"gender|g[êe]nero|\brace\b|ra[çc]a|hispanic|latino|\bveteran\b|veteran[oa]|"
    r"disabilit|defici[êe]nc|\breferences?\b|refer[êe]ncias?",
    re.IGNORECASE,
)


def is_bank_eligible(kind: QuestionKind) -> bool:
    return kind in _BANK_ELIGIBLE_KINDS


def is_sensitive_label(label: str) -> bool:
    """A label naming a demographic/EEO category or third-party references —
    never eligible for the cross-job bank regardless of question kind, because
    nothing deterministic stops the LLM from guessing an answer to a label
    like this even though the underlying data is deliberately excluded from
    its prompt (profile.py's profile_for_answers). A hallucinated answer here
    must not persist into a table shared across every future company."""
    return bool(_SENSITIVE_LABEL.search(label))


def normalize_question(label: str) -> str:
    text = _WHITESPACE.sub(" ", label.strip()).lower()
    return _TRAILING_PUNCTUATION.sub("", text).strip()


def load_answer_bank() -> dict[str, str]:
    """Every banked answer, keyed by normalised question. The table is small
    (Alberto's own repeat screening questions) — loading it whole is simpler
    than a per-question query and cheap at this scale."""
    # Local import, same layering reason as composer.py's cvgen import: this
    # module's pure helpers (normalize_question, is_bank_eligible,
    # is_sensitive_label) are imported by composer.py, which the plan requires
    # to do no DB access "directly or via import". A module-level
    # `from moonlighter.core.db import AnswerBankEntry` made importing the
    # composer pull in peewee and the whole DB layer.
    from moonlighter.core.db import AnswerBankEntry

    return {row.normalized_question: row.answer for row in AnswerBankEntry.select()}


def promote_application(job_cache: dict[str, Any], source_job_id: int) -> None:
    """Upserts every bank-eligible entry of a per-job cache into the shared table.

    `job_cache` comes straight off Application.get_form_data() — a JSON blob
    whose shape predates this feature in some existing test fixtures (a flat
    label->string mapping). Anything not shaped like {"answer": str, "kind":
    str} is skipped rather than raising: this is defensive against that
    legacy shape, not validation of untrusted input.
    """
    from moonlighter.core.db import AnswerBankEntry  # local: see load_answer_bank

    for label, entry in job_cache.items():
        if not isinstance(entry, dict) or "answer" not in entry or "kind" not in entry:
            continue
        try:
            kind = QuestionKind(entry["kind"])
        except ValueError:
            continue
        if not is_bank_eligible(kind):
            continue
        if is_sensitive_label(label):
            # Kind alone does not protect these: a demographic or references
            # question is usually TEXT or SINGLE_SELECT, i.e. bank-eligible.
            continue
        normalized = normalize_question(label)
        row, created = AnswerBankEntry.get_or_create(
            normalized_question=normalized,
            defaults={
                "kind": kind.value,
                "answer": entry["answer"],
                "source_job_id": source_job_id,
            },
        )
        if not created:
            row.kind = kind.value
            row.answer = entry["answer"]
            row.source_job_id = source_job_id
            row.updated_at = datetime.now()
            row.save()
