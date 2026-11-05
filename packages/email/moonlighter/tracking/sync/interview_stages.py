"""Learning the interview stages an email proposes, bounded because an email is untrusted."""

import re
from typing import Any

_MAXIMUM_STAGE_LENGTH = 40
_MAXIMUM_STAGES = 40

_STAGE_ALLOWED = re.compile(r"[^a-z0-9]+")


def _sanitize_stage(raw: str | None) -> str | None:
    """Normalize an LLM-proposed stage to a bounded ``[a-z0-9_]`` slug.

    An email is untrusted input: a prompt-injected classification can propose an
    arbitrary ``new_stage``. Reducing it to a lowercase snake_case slug of at most
    ``_MAXIMUM_STAGE_LENGTH`` chars strips special characters and bounds length, so a
    persisted stage cannot carry a payload back into a later prompt. Snake_case
    matches this project's stage naming convention (e.g. ``phone_screening``),
    so a newly registered stage matches the same email's ``stage`` value. Returns
    ``None`` when nothing usable remains or the slug is over-length.
    """
    if not raw:
        return None
    slug = _STAGE_ALLOWED.sub("_", raw.lower()).strip("_")
    if not slug or len(slug) > _MAXIMUM_STAGE_LENGTH:
        return None
    return slug


def register_new_stage(
    new_stage: str | None, stages: list[str], email_config: dict[str, Any]
) -> None:
    """Learn a novel stage proposed by the LLM, persisting it to the in-memory config.

    The candidate is sanitized to a bounded slug (untrusted email input) and only
    registered while the stage list is below ``_MAXIMUM_STAGES``, so a hostile email
    cannot inject arbitrary text or grow the config without bound.
    """
    slug = _sanitize_stage(new_stage)
    if slug is None or slug in stages or len(stages) >= _MAXIMUM_STAGES:
        return
    stages.append(slug)
    email_config["interview_stages"] = stages
