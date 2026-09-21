"""Drafts a CV pool + fills the generic template from a user's own profile.yaml.

The bootstrap is the "onboarding" half of the tailored-CV feature (the other
half, cvgen/service.py's ensure_tailored_cv, only ever SELECTS from an
already-curated pool). Here the model genuinely authors the first draft's
text -- Alberto's own framing is "a first draft you edit" -- so every
generated bullet still goes through the same escape_latex/is_typesettable
guard real curated content is held to before it ever reaches a .yaml file,
and the written pool carries an explicit DRAFT header (see
bootstrap_cv_pool, Task 6) instead of any code-level lock on first use."""

import importlib.resources
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moonlighter.application.answers.profile import profile_for_answers
from moonlighter.application.cvgen.compile import compile_pdf
from moonlighter.application.cvgen.pool import CVPool, PoolBullet, PoolExperience, dump_pool
from moonlighter.application.cvgen.render import escape_latex, is_typesettable
from moonlighter.application.cvgen.service import resolved_pool_path, resolved_template_dir
from moonlighter.core.llm import LLMCaller, is_spend_limit
from moonlighter.core.log import get_logger
from moonlighter.core.parsing import parse_llm_json

logger = get_logger(__name__)


class BootstrapError(Exception):
    """The bootstrap could not produce a usable draft -- named precisely so
    the MCP tool / CLI subcommand can report why, instead of a bare crash."""


# pool.py's load_pool requires every experience to carry a non-empty
# location (its own _fixed_field/`not raw.get(field)` check) -- but a
# profile.yaml with neither a top-level "location" nor a per-entry one is a
# realistic bootstrap input, not a malformed one. Falling all the way to ""
# would write a pool that dump_pool can produce but load_pool then refuses
# to read back, breaking the very next ensure_tailored_cv call. A placeholder
# the operator will visibly want to replace is safer than an empty field
# that silently breaks the pool on first reload.
_UNKNOWN_LOCATION = "Not specified"


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
        company=escape_latex(str(raw["company"])),
        title=escape_latex(str(raw.get("title") or "")),
        period=escape_latex(str(raw.get("period") or "")),
        location=escape_latex(str(raw.get("location") or default_location or _UNKNOWN_LOCATION)),
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


DRAFT_HEADER = (
    "# DRAFT — review before using this for a real application\n"
    "# Generated by moonlighter's CV-pool bootstrap from your profile.yaml.\n"
    "# Read every bullet before your first real application uses it.\n\n"
)

_LINKEDIN_USERNAME = re.compile(r"linkedin\.com/in/([^/?#]+)")


def _split_name(name: str) -> tuple[str, str]:
    parts = name.strip().rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (name.strip(), "")


def _linkedin_username(url: str) -> str:
    m = _LINKEDIN_USERNAME.search(url)
    return m.group(1).rstrip("/") if m else ""


def _education_block(entries: list[Any]) -> str:
    # year/degree/school are pasted into \cventry{...} the same way pool.py's
    # curated company/title/location are (see that module's own docstring for
    # the "R&D Engineer" incident this class of bug already caused once) --
    # profile.yaml is operator-authored free text, not pre-escaped LaTeX, so
    # every field goes through escape_latex exactly like the contact fields
    # below.
    lines = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        year = escape_latex(str(e.get("year") or ""))
        degree = escape_latex(str(e.get("degree") or ""))
        school = escape_latex(str(e.get("school") or ""))
        lines.append(f"\\cventry{{{year}}}{{{degree}}}{{{school}}}{{}}{{}}{{}}")
    return "\n".join(lines)


def fill_template(profile: dict[str, Any]) -> str:
    """Fills the shipped generic template's ONE-TIME {{...}} placeholders from
    profile.yaml -- name/contact/education, all deterministic substitution,
    no LLM call. The four per-job %%...%% markers are untouched: they are
    filled on every prepare_application call, by render_cv, not here."""
    templates = importlib.resources.files("moonlighter.application.cvgen.templates")
    text = (templates / "cv-template.en.example.tex").read_text()
    first, last = _split_name(str(profile.get("name") or ""))
    # These five substitute into ordinary text-mode LaTeX macros (\firstname{},
    # \title{}, \phone[mobile]{}, \email{}), never verbatim -- an unescaped
    # '&'/'%'/'_' from a profile field either breaks the compile or, worse, a
    # bare '%' silently truncates the rest of the line (LaTeX's comment
    # character) with no compile error at all. escape_latex is what pool.py's
    # own curated fields and every model-authored string in render.py already
    # go through before reaching a .tex file; profile.yaml is exactly as
    # untrusted as either. LINKEDIN_USERNAME is the one exception: it is a
    # slug already parsed out of a URL by _linkedin_username, never free text,
    # and moderncv's \social[linkedin]{...} expects exactly that bare slug.
    return (
        text.replace("{{NAME_FIRST}}", escape_latex(first))
        .replace("{{NAME_LAST}}", escape_latex(last))
        .replace("{{HEADLINE}}", escape_latex(str(profile.get("headline") or "")))
        .replace("{{PHONE}}", escape_latex(str(profile.get("phone") or "")))
        .replace("{{EMAIL}}", escape_latex(str(profile.get("email") or "")))
        .replace("{{LINKEDIN_USERNAME}}", _linkedin_username(str(profile.get("linkedin") or "")))
        .replace("{{EDUCATION}}", _education_block(profile.get("education") or []))
    )


@dataclass(frozen=True)
class BootstrapOutcome:
    pool_path: Path
    template_path: Path
    pdf_path: Path | None
    bullet_count: int


async def bootstrap_cv_pool(
    profile: dict[str, Any], config: dict[str, Any], caller: LLMCaller, *, force: bool = False
) -> BootstrapOutcome:
    """Draft a CV pool + adapt the generic template from `profile`, writing
    both to the config's (or default) paths -- the shared function both the
    MCP tool and the CLI subcommand call, so neither reimplements the other."""
    pool_path = resolved_pool_path(config)
    if pool_path.exists() and not force:
        raise BootstrapError(
            f"a CV pool already exists at {pool_path} — pass force=True to overwrite it"
        )
    pool = await draft_pool(profile, caller)
    pool_path.parent.mkdir(parents=True, exist_ok=True)
    pool_path.write_text(DRAFT_HEADER + dump_pool(pool))

    template_dir = resolved_template_dir(config)
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path = template_dir / "cv-template.en.tex"
    template_path.write_text(fill_template(profile))

    pdf_path = compile_pdf(template_path)
    bullet_count = sum(len(e.bullets) for e in pool.experiences) + len(pool.open_source)
    return BootstrapOutcome(
        pool_path=pool_path,
        template_path=template_path,
        pdf_path=pdf_path,
        bullet_count=bullet_count,
    )
