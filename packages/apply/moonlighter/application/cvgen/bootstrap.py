"""Drafts a CV pool + fills the generic template from a user's own profile.yaml.

The bootstrap is the "onboarding" half of the tailored-CV feature (the other
half, cvgen/service.py's ensure_tailored_cv, only ever SELECTS from an
already-curated pool). Here the model genuinely authors the first draft's
text -- Alberto's own framing is "a first draft you edit" -- so every
generated bullet still goes through the same escape_latex/is_typesettable
guard real curated content is held to before it ever reaches a .yaml file,
and the written pool carries an explicit DRAFT header (see
bootstrap_cv_pool, Task 6) instead of any code-level lock on first use."""

from typing import Any

from moonlighter.application.answers.profile import profile_for_answers
from moonlighter.application.cvgen.pool import CVPool, PoolBullet, PoolExperience
from moonlighter.application.cvgen.render import escape_latex, is_typesettable
from moonlighter.core.llm import LLMCaller, is_spend_limit
from moonlighter.core.log import get_logger
from moonlighter.core.parsing import parse_llm_json

logger = get_logger(__name__)


class BootstrapError(Exception):
    """The bootstrap could not produce a usable draft -- named precisely so
    the MCP tool / CLI subcommand can report why, instead of a bare crash."""


_PROMPT = """You are drafting a first CV bullet pool from this candidate's profile, for them
to review and edit -- you are NOT selecting for one specific job posting.

## The candidate's profile
{profile}

## Instructions
Turn each entry in the profile's "experience" list into a CV entry with 1-3 bullets, each
built ONLY from that entry's own highlights/description -- never invent an achievement, a
number, or a technology the profile does not state. Tag each bullet with 1-3 "angles" from
this set: backend, frontend, ai, leadership, education, data. If an experience entry has no
"location" field, this candidate is generally based in: {default_location}.

Answer JSON only, no markdown fence:
{{"experiences": [
    {{"company": "...", "title": "...", "period": "...", "location": "..." (optional, see above),
      "bullets": [{{"id": "kebab-case-id-unique-in-this-response", "angles": ["..."],
                    "text": "plain text, **bold** for emphasis, built only from this entry"}}]}}],
 "open_source": [{{"id": "...", "angles": ["..."], "text": "..."}}]
   (from the profile's own open_source entries, if any -- else []),
 "summary_facts": ["short plain-text facts a later per-job summary generator may cite"]}}

Write every "text" value as PLAIN TEXT: no LaTeX, no backslashes, no braces -- **bold** is the
only markup allowed, the same dialect a professional summary would use."""


def _prefix(profile: dict[str, Any]) -> str:
    curated = profile_for_answers(profile)
    default_location = str(profile.get("location") or "not specified")
    return _PROMPT.format(profile=str(curated), default_location=default_location)


def _dedupe_id(candidate: str, seen: set[str]) -> str:
    if candidate not in seen:
        seen.add(candidate)
        return candidate
    n = 2
    while f"{candidate}-{n}" in seen:
        n += 1
    deduped = f"{candidate}-{n}"
    seen.add(deduped)
    return deduped


def _bullet_from_raw(raw: Any, seen_ids: set[str]) -> PoolBullet | None:
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text") or "")
    if not text.strip() or not is_typesettable(text):
        logger.warning(
            "bootstrap: dropping a non-typesettable or empty bullet (id=%r)", raw.get("id")
        )
        return None
    latex = escape_latex(text)
    if not latex:
        return None
    raw_id = str(raw.get("id") or "bullet")
    angles = tuple(str(a) for a in raw.get("angles") or ())
    return PoolBullet(id=_dedupe_id(raw_id, seen_ids), angles=angles, latex=latex)


def _experience_from_raw(
    raw: Any, default_location: str, seen_ids: set[str]
) -> PoolExperience | None:
    if not isinstance(raw, dict) or not raw.get("company"):
        return None
    bullets = tuple(
        b
        for b in (_bullet_from_raw(r, seen_ids) for r in raw.get("bullets") or [])
        if b is not None
    )
    if not bullets:
        return None
    return PoolExperience(
        company=str(raw["company"]),
        title=str(raw.get("title") or ""),
        period=str(raw.get("period") or ""),
        location=str(raw.get("location") or default_location),
        bullets=bullets,
        prose=None,
        prose_id=None,
        angles=(),
    )


async def draft_pool(profile: dict[str, Any], caller: LLMCaller) -> CVPool:
    if not profile.get("experience"):
        raise BootstrapError("the profile has no experience entries to draft a CV pool from")
    try:
        raw_response = await caller(_prefix(profile), "claude-sonnet-4-6")
    except Exception as e:
        if is_spend_limit(e):
            raise  # the caller decides whether to retry later, same as everywhere else
        raise BootstrapError(f"the CV-pool drafting call failed: {e}") from e
    try:
        data = parse_llm_json(raw_response)
    except Exception as e:
        raise BootstrapError(f"the model's response could not be parsed as JSON: {e}") from e
    if not isinstance(data, dict) or not data.get("experiences"):
        raise BootstrapError("the model's response could not be parsed into a CV pool")

    default_location = str(profile.get("location") or "")
    seen_ids: set[str] = set()
    experiences = tuple(
        e
        for e in (
            _experience_from_raw(raw, default_location, seen_ids) for raw in data["experiences"]
        )
        if e is not None
    )
    if not experiences:
        raise BootstrapError("no usable experience entries survived drafting")
    open_source = tuple(
        b
        for b in (_bullet_from_raw(r, seen_ids) for r in data.get("open_source") or [])
        if b is not None
    )
    summary_facts = tuple(str(f) for f in data.get("summary_facts") or [])
    return CVPool(experiences=experiences, open_source=open_source, summary_facts=summary_facts)
