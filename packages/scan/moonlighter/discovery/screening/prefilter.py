"""What can be decided about a posting without spending an LLM token."""

from dataclasses import dataclass
from typing import Any

from moonlighter.core.db import Job
from moonlighter.discovery.evaluation.title_filter import should_skip_by_title
from moonlighter.discovery.scan.claims import claim
from moonlighter.discovery.scan.persistence import archived_fields, needs_review_fields, persist
from moonlighter.discovery.screening.eligibility import (
    Eligibility,
    classify_location,
    eligible_regions_from,
)
from moonlighter.discovery.screening.evaluator_inputs import is_description_insufficient
from moonlighter.discovery.sources.base import RawJob


@dataclass(frozen=True)
class ScreeningRules:
    """The profile and config facts the free checks read."""

    blocklist: list[str]
    home_city: str | None
    eligible_regions: tuple[str, ...]


def screening_rules(config: dict[str, Any], profile: dict[str, Any]) -> ScreeningRules:
    """The rules a scan screens its postings with."""
    return ScreeningRules(
        blocklist=config.get("title_blocklist", []),
        home_city=(profile.get("criteria") or {}).get("home_city"),
        eligible_regions=eligible_regions_from(profile),
    )


def _fields_without_llm(raw: RawJob, rules: ScreeningRules) -> dict[str, Any] | None:
    """The fields a posting is saved with when a free check decides it, else None."""
    matched = should_skip_by_title(raw.title, rules.blocklist)
    if matched:
        return archived_fields(f"title filtered: {matched!r}")
    if (
        classify_location(
            raw.location, raw.remote_type, rules.home_city, eligible_regions=rules.eligible_regions
        )
        is Eligibility.INELIGIBLE
    ):
        # Onsite/hybrid outside the profile's home city: no JD wording
        # can fix that — archived without an LLM call (see eligibility.py).
        return archived_fields(f"location ineligible: {raw.location!r}")
    if is_description_insufficient(raw.description):
        return needs_review_fields("description unavailable — needs manual verification")
    return None


def screen_chunk(chunk: list[RawJob], rules: ScreeningRules) -> tuple[list[Job], list[RawJob]]:
    """Claim and screen a chunk: the jobs saved without the LLM, and the ones left to evaluate."""
    saved: list[Job] = []
    to_evaluate: list[RawJob] = []
    for raw in chunk:
        if not claim(raw):
            continue  # already reserved (race/previous scan)
        fields = _fields_without_llm(raw, rules)
        if fields is None:
            to_evaluate.append(raw)
            continue
        job = persist(raw, **fields)
        if job is not None:
            saved.append(job)
    return saved, to_evaluate


def park_unevaluated(raw_jobs: list[RawJob]) -> list[Job]:
    """Save the evaluable jobs as needs_review, for --no-eval.

    Nothing here may cost a token. They are parked the way a missing description
    already is, so verify_job can score them later from a pasted page.
    """
    parked = (persist(raw, **needs_review_fields("not evaluated (--no-eval)")) for raw in raw_jobs)
    return [job for job in parked if job is not None]
