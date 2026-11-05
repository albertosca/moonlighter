"""The value objects of job evaluation: what goes in and what comes out."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalInput:
    """Input for batch evaluation: company, title, description and location fields.

    The structured location fields are the ones the boards publish (see eligibility.py — the
    LLM judging eligibility without seeing them caused the 32/32 gitlab
    false positives of 2026-08-21).
    """

    company: str
    title: str
    description: str
    location: str | None = None
    remote_type: str | None = None


@dataclass
class EvaluationResult:
    score: float
    score_notes: str
    caveats: list[str] = field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_source: str | None = None
