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

from datetime import datetime, timedelta
from typing import Any

from moonlighter.application.answers.bank_eligibility import (
    is_bank_eligible,
    is_sensitive_label,
    normalize_question,
)
from moonlighter.application.assisted.questions import QuestionKind
from moonlighter.core.db import AnswerBankEntry


def load_answer_bank(maximum_age_days: int | None) -> dict[str, str]:
    """Every banked answer no older than maximum_age_days, keyed by normalised question.

    None disables expiry. The table is small (Alberto's own repeat
    screening questions) — loading it whole is simpler than a per-question
    query and cheap at this scale.

    Age is measured from updated_at, which every promotion refreshes, so an
    answer that keeps getting used never expires — only one nobody has
    submitted in that long does. Nothing is deleted: a stale row is skipped
    here and overwritten by the next promotion of the same question.
    """
    rows = AnswerBankEntry.select()
    if maximum_age_days is not None:
        cutoff = datetime.now() - timedelta(days=maximum_age_days)  # noqa: DTZ005 - the database stores naive local time
        rows = rows.where(AnswerBankEntry.updated_at >= cutoff)
    return {row.normalized_question: row.answer for row in rows}


def promote_application(job_cache: dict[str, Any], source_job_id: int) -> None:
    """Upserts every bank-eligible entry of a per-job cache into the shared table.

    `job_cache` comes straight off Application.get_form_data() — a JSON blob
    whose shape predates this feature in some existing test fixtures (a flat
    label->string mapping). Anything not shaped like {"answer": str, "kind":
    str} is skipped rather than raising: this is defensive against that
    legacy shape, not validation of untrusted input.
    """
    for label, entry in job_cache.items():
        kind = _bankable_kind(label, entry)
        if kind is None:
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
            row.updated_at = datetime.now()  # noqa: DTZ005 - the database stores naive local time
            row.save()


def _bankable_kind(label: str, entry: object) -> QuestionKind | None:
    """The kind to bank `entry` under, or None when it must stay out of the bank."""
    kind = _entry_kind(entry)
    if kind is None or not is_bank_eligible(kind):
        return None
    if is_sensitive_label(label):
        # Kind alone does not protect these: a demographic or references
        # question is usually TEXT or SINGLE_SELECT, i.e. bank-eligible.
        return None
    return kind


def _entry_kind(entry: object) -> QuestionKind | None:
    """The kind of a per-job cache entry shaped {"answer": ..., "kind": ...}, else None."""
    if not isinstance(entry, dict) or "answer" not in entry or "kind" not in entry:
        return None
    try:
        return QuestionKind(entry["kind"])
    except ValueError:
        return None


def list_entries() -> list[AnswerBankEntry]:
    """Every banked answer, most recently used first.

    That is the order the operator wants when asking "what would replay right now?".
    """
    return list(AnswerBankEntry.select().order_by(AnswerBankEntry.updated_at.desc()))


def forget(question: str) -> bool:
    """Delete the banked answer for `question`, normalised the way the bank keys it.

    False when nothing matched. The next application that asks it goes to the
    LLM again and, once submitted, re-banks whatever it answered.
    """
    deleted: int = (
        AnswerBankEntry.delete()
        .where(AnswerBankEntry.normalized_question == normalize_question(question))
        .execute()
    )
    return deleted > 0


def render_answer_bank(rows: list[AnswerBankEntry], maximum_age_days: int | None) -> str:
    """One line per entry.

    An entry past maximum_age_days is kept but marked, since "why wasn't this
    replayed?" is the question that brings an operator here.
    """
    if not rows:
        return "The answer bank is empty."
    cutoff = (
        None if maximum_age_days is None else datetime.now() - timedelta(days=maximum_age_days)  # noqa: DTZ005 - the database stores naive local time
    )
    noun = "entry" if len(rows) == 1 else "entries"
    lines = [f"# Answer bank — {len(rows)} {noun}\n"]
    for row in rows:
        expired = cutoff is not None and row.updated_at < cutoff
        flag = "  (expired — not replayed)" if expired else ""
        lines.append(
            f"- **{row.normalized_question}** → {row.answer}  "
            f"[{row.kind}, job #{row.source_job_id}, last used {row.updated_at:%Y-%m-%d}]{flag}"
        )
    return "\n".join(lines)
