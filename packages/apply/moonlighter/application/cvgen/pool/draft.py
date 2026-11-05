"""Drafts a CV bullet pool from a candidate's profile with one model call.

The model genuinely authors this first draft's text, so every bullet goes
through the same escape_latex/is_typesettable guard real curated content is
held to before it can reach a .yaml file.
"""

from typing import Any

from moonlighter.application.answers.answer_profile import profile_for_answers
from moonlighter.application.cvgen.latex.text import escape_latex, is_typesettable
from moonlighter.application.cvgen.pool.bootstrap_error import BootstrapError
from moonlighter.application.cvgen.pool.loader import CVPool, PoolBullet, PoolExperience
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.spend_limit import is_spend_limit
from moonlighter.core.log import get_logger
from moonlighter.core.parsing import parse_llm_json

logger = get_logger(__name__)

# pool.py's load_pool requires every experience to carry a non-empty
# company, title, period AND location (one `not raw.get(field)` check over
# all four) -- but a profile.yaml missing any of them is a realistic
# bootstrap input, not a malformed one, and so is a model that omits one
# from its answer. Falling all the way to "" would write a pool that
# dump_pool can produce but load_pool then refuses to read back, breaking
# the very next ensure_tailored_cv call. A placeholder the operator will
# visibly want to replace is safer than an empty field that silently breaks
# the pool on first reload. (Company is not in this list on purpose:
# _experience_from_raw drops an entry with no company outright -- there is
# nothing to place-hold, the entry names no job.)
_UNKNOWN_LOCATION = "Not specified"
_UNKNOWN_TITLE = "Title not specified"
_UNKNOWN_PERIOD = "Period not specified"


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
    suffix = 2
    while f"{candidate}-{suffix}" in seen:
        suffix += 1
    deduped = f"{candidate}-{suffix}"
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
    angles = tuple(str(angle) for angle in raw.get("angles") or ())
    return PoolBullet(id=_dedupe_id(raw_id, seen_ids), angles=angles, latex=latex)


def _bullets_from_raw(raw_bullets: Any, seen_ids: set[str]) -> tuple[PoolBullet, ...]:
    drafted = (_bullet_from_raw(raw_bullet, seen_ids) for raw_bullet in raw_bullets or [])
    return tuple(bullet for bullet in drafted if bullet is not None)


def _experience_from_raw(
    raw: Any, default_location: str, seen_ids: set[str]
) -> PoolExperience | None:
    if not isinstance(raw, dict) or not raw.get("company"):
        return None
    bullets = _bullets_from_raw(raw.get("bullets"), seen_ids)
    if not bullets:
        return None
    return PoolExperience(
        company=escape_latex(str(raw["company"])),
        title=escape_latex(str(raw.get("title") or _UNKNOWN_TITLE)),
        period=escape_latex(str(raw.get("period") or _UNKNOWN_PERIOD)),
        location=escape_latex(str(raw.get("location") or default_location or _UNKNOWN_LOCATION)),
        bullets=bullets,
        prose=None,
        prose_id=None,
        angles=(),
    )


async def _drafted_data(profile: dict[str, Any], caller: LLMCaller) -> dict[str, Any]:
    """The model's drafted pool as a dict, or a BootstrapError saying why not."""
    try:
        raw_response = await caller(_prefix(profile), "claude-sonnet-4-6")
    except Exception as error:
        if is_spend_limit(error):
            raise  # the caller decides whether to retry later, same as everywhere else
        raise BootstrapError(f"the CV-pool drafting call failed: {error}") from error
    try:
        data = parse_llm_json(raw_response)
    except Exception as error:
        raise BootstrapError(
            f"the model's response could not be parsed as JSON: {error}"
        ) from error
    if not isinstance(data, dict) or not data.get("experiences"):
        raise BootstrapError("the model's response could not be parsed into a CV pool")
    return data


async def draft_pool(profile: dict[str, Any], caller: LLMCaller) -> CVPool:
    if not profile.get("experience"):
        raise BootstrapError("the profile has no experience entries to draft a CV pool from")
    data = await _drafted_data(profile, caller)

    default_location = str(profile.get("location") or "")
    seen_ids: set[str] = set()
    drafted = (_experience_from_raw(raw, default_location, seen_ids) for raw in data["experiences"])
    experiences = tuple(experience for experience in drafted if experience is not None)
    if not experiences:
        raise BootstrapError("no usable experience entries survived drafting")
    open_source = _bullets_from_raw(data.get("open_source"), seen_ids)
    summary_facts = tuple(str(fact) for fact in data.get("summary_facts") or [])
    return CVPool(experiences=experiences, open_source=open_source, summary_facts=summary_facts)
