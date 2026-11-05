"""The slice of the profile that is worth sending to the model."""

from typing import Any

# Profile fields that matter for SCORING a job. Contact/credentials
# (name/phone/email/linkedin) and education/publications don't influence the score
# and only bloat the prompt — left out. `open_source` stays in: public projects are
# evidence for requirements the experience list may not name (Encora, 2026-09-24).
_EVAL_PROFILE_KEYS = (
    "criteria",
    "skills",
    "headline",
    "summary",
    "preferences",
    "languages",
    "experience",
    "open_source",
)


def profile_for_eval(profile: dict[str, Any]) -> dict[str, Any]:
    """Subset of the profile relevant to evaluation.

    Reduces tokens per call without losing the dealbreakers (criteria) or the match context
    (skills/experience).
    """
    return {key: profile[key] for key in _EVAL_PROFILE_KEYS if key in profile}
