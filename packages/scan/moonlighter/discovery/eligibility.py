"""Deterministic regional-eligibility classification from structured fields.

Provenance: live incident 2026-08-20/21 (job 7733, then the whole gitlab
cluster — 32/32 false positives in the 21/08 manual triage). The eligibility
hard filter lived only in the evaluator prompt, which sees the DESCRIPTION;
on boards like GitLab the region lives in the posting's location field
("Bangalore, India"), which the LLM never saw.

The home city comes from the profile (`criteria.home_city`). Only the
impossible is cut without the LLM: onsite/hybrid outside the home city cannot
be worked from there no matter what the JD says. With no home city (the
default for any user who has not set one) nothing is cut by location. A location
that merely names a foreign place stays AMBIGUOUS — the documented Colombia
case ("Colombia" in the field, "work remotely from anywhere in LATAM" in the
JD) would be silently archived by a blind country cut, and a false INELIGIBLE
costs a good job while a false AMBIGUOUS costs one LLM call that now SEES the
location field.
"""

import re
from enum import StrEnum


class Eligibility(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    AMBIGUOUS = "ambiguous"


_ELIGIBLE_REGION = re.compile(
    r"\bbra[sz]il\b|\blatam\b|latin america|south america|\bamericas\b"
    r"|\bworldwide\b|\bglobal\b|\banywhere\b",
    re.IGNORECASE,
)
_ONSITE_KINDS = frozenset({"onsite", "hybrid"})


def classify_location(
    location: str | None, remote_type: str | None, home_city: str | None = None
) -> Eligibility:
    """Classify a posting's structured location/remote_type against the rule above.

    ELIGIBLE and INELIGIBLE are decided here, without the LLM; AMBIGUOUS falls
    through to the evaluator, whose prompt now carries both fields.
    """
    if not location or not location.strip():
        return Eligibility.AMBIGUOUS
    home = (home_city or "").strip().casefold()
    if home and home in location.casefold():
        return Eligibility.ELIGIBLE
    if home and remote_type in _ONSITE_KINDS:
        # A named place that is not the home city, explicitly on-site or
        # hybrid: no JD wording can make that workable from home.
        return Eligibility.INELIGIBLE
    if _ELIGIBLE_REGION.search(location):
        return Eligibility.ELIGIBLE
    return Eligibility.AMBIGUOUS
