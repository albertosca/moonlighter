"""
Curates the profile down to the fields safe to hand the LLM when it writes
free-text application answers.
"""

from typing import Any

# Least privilege for the answer path: the model writes free-text that gets typed onto the
# employer's page, so it must not carry the operator's secrets. It needs only prose-relevant
# fields. Contact fields are filled statically by field_map (no LLM); salary/target/criteria
# are negotiating leverage with no use in writing an answer. Sibling of evaluator's
# profile_for_eval — different key set because the threats differ (the evaluator's output is a
# clamped number; this path's output is free text on an untrusted page).
_ANSWER_PROFILE_KEYS = (
    # The experience list starts at the first formal contract, so counting from it
    # understates a career that began earlier (internships, early roles). Without
    # this the model wrote "close to 14 years" for someone with 16 — in a
    # screening question that asks precisely that.
    "career_started",
    "headline",
    "summary",
    "skills",
    "experience",
    "education",
    "languages",
    "publications",
    # Seen live twice on 2026-08-21 (Supabase #8138/#5100): "open source
    # contributions" answers ignored the projects in open_source: because the
    # whitelist never let them through. Prose content, public by nature —
    # links stay on the deterministic field-map track.
    "open_source",
)


def profile_for_answers(profile: dict[str, Any]) -> dict[str, Any]:
    """Return only the profile fields the model needs to write prose answers."""
    return {k: profile[k] for k in _ANSWER_PROFILE_KEYS if k in profile}
