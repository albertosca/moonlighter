"""The value objects of job evaluation: what goes in and what comes out."""

from dataclasses import KW_ONLY, dataclass, field


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
    _: KW_ONLY
    # Required on purpose, even as None, and by name only: an optional default let a
    # caller drop them silently and the regional filter degraded to the description
    # alone (2026-09-25 re-eval: 4 of 6 promoted jobs were false positives).
    location: str | None
    remote_type: str | None


@dataclass
class EvaluationResult:
    score: float
    score_notes: str
    caveats: list[str] = field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_source: str | None = None
