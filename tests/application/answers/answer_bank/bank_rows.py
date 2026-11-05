"""Answer-bank rows the tests seed, aged from now or dated against a frozen clock."""

from datetime import datetime, timedelta

from moonlighter.core.db import AnswerBankEntry

FROZEN_NOW = datetime(2026, 11, 5, 12, 0, 0)  # noqa: DTZ001 - the database stores naive local time
SEPTEMBER_FIRST = FROZEN_NOW - timedelta(days=65)
JANUARY_SECOND = FROZEN_NOW - timedelta(days=307)


def aged_entry(question: str, answer: str, days_old: int) -> None:
    """Bank a text answer last used ``days_old`` days before the real now."""
    AnswerBankEntry.create(
        normalized_question=question,
        kind="text",
        answer=answer,
        source_job_id=1,
        updated_at=datetime.now() - timedelta(days=days_old),  # noqa: DTZ005 - the database stores naive local time
    )


def dated_entry(question: str, answer: str, updated_at: datetime, *, kind: str = "text") -> None:
    """Bank an answer last used at an exact moment, for the frozen-clock pins."""
    AnswerBankEntry.create(
        normalized_question=question,
        kind=kind,
        answer=answer,
        source_job_id=1,
        updated_at=updated_at,
    )
