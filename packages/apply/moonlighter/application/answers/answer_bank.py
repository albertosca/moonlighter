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
from moonlighter.core.db import AnswerBankEntry

_BANK_ELIGIBLE_KINDS = frozenset(
    {QuestionKind.TEXT, QuestionKind.BOOLEAN, QuestionKind.SINGLE_SELECT, QuestionKind.MULTI_SELECT}
)
_WHITESPACE = re.compile(r"\s+")
_TRAILING_PUNCTUATION = re.compile(r"[?:*]+$")


def is_bank_eligible(kind: QuestionKind) -> bool:
    return kind in _BANK_ELIGIBLE_KINDS


def normalize_question(label: str) -> str:
    text = _WHITESPACE.sub(" ", label.strip()).lower()
    return _TRAILING_PUNCTUATION.sub("", text).strip()


def load_answer_bank() -> dict[str, str]:
    """Every banked answer, keyed by normalised question. The table is small
    (Alberto's own repeat screening questions) — loading it whole is simpler
    than a per-question query and cheap at this scale."""
    return {row.normalized_question: row.answer for row in AnswerBankEntry.select()}


def promote_application(job_cache: dict[str, Any], source_job_id: int) -> None:
    """Upserts every bank-eligible entry of a per-job cache into the shared table.

    `job_cache` comes straight off Application.get_form_data() — a JSON blob
    whose shape predates this feature in some existing test fixtures (a flat
    label->string mapping). Anything not shaped like {"answer": str, "kind":
    str} is skipped rather than raising: this is defensive against that
    legacy shape, not validation of untrusted input.
    """
    for label, entry in job_cache.items():
        if not isinstance(entry, dict) or "answer" not in entry or "kind" not in entry:
            continue
        try:
            kind = QuestionKind(entry["kind"])
        except ValueError:
            continue
        if not is_bank_eligible(kind):
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
